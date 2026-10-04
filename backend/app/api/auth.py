# Mission Sécurité — échange JWT Neon ↔ cookie HttpOnly.
#
# POURQUOI CETTE ROUTE EXISTE
#
# Le JWT Neon était envoye en `Authorization: Bearer` par le front. Ce
# header est lisible par TOUT : l'onglet Network des DevTools, une
# ligne de console, et surtout n'importe quel script injecté dans la
# page — un XSS n'avait qu'à lire `window.__neonGetToken()` pour
# exfiltrer une session de 15 minutes entière.
#
# Un cookie HttpOnly coupe ce chemin : le JavaScript de la page ne peut
# pas le lire, et le seul moyen de le voler est de l'envoyer ailleurs.
#
# Le cookie est posé ICI, et non par Neon Auth, pour une raison
# précise : le cookie de session de Better Auth vit sur le domaine Neon
# (`*.neon.tech`), pas sur le nôtre. Notre backend ne contrôle donc ni
# ses drapeaux ni sa durée de vie — et ne pourrait pas le poser en
# HttpOnly de toute façon.
#
# Ce que le cookie N'EST PAS : une session longue durée. Il ne fait que
# REFLETER le JWT, dont la durée de vie est de 15 minutes. La session
# de 30 à 90 jours reste celle de Better Auth, côté Neon. Notre cookie
# est un jeton court que le front renouvelle en silence (voir
# NeonTokenBridge : RENEWAL_WINDOW_MS).
#
# Why SameSite=None et pas Lax : le front est hébergé sur
# `*.vercel.app` et l'API sur `*.onrender.com`. Deux sites différents.
# Un cookie SameSite=Lax n'est PAS envoyé sur une requête cross-site :
# l'utilisateur serait déconnecté à chaque appel. Le couple
# `SameSite=None; Secure` est donc obligatoire ici — et c'est
# précisément ce qui rend la protection CSRF indispensable
# (cf. le middleware `enforce_origin` dans app/main.py).
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError

from app.auth.resolver import (
    AUTH_COOKIE_NAME,
    AUTH_COOKIE_PATH,
    AUTH_COOKIE_SAMESITE,
    AUTH_COOKIE_SECURE,
    extract_token,
    verify_neon_token,
)
from app.config import log_safe
from app.logging.events import log_event

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SessionExchange(BaseModel):
    """Corps de POST /api/auth/session — le JWT à échanger."""

    token: str = Field(..., min_length=1, description="JWT Neon Ed25519")


class SessionStatus(BaseModel):
    authenticated: bool
    expires_in: int | None = Field(
        default=None,
        description=(
            "Secondes restantes avant expiration du cookie "
            "( = durée de vie restante du JWT )."
        ),
    )


def _remaining_seconds(claims: dict) -> int:
    """Durée de vie RESTANTE du JWT, en secondes entières.

    On ne se fie jamais à une constante : un cookie dont Max-Age
    dépasserait la vie de son propre JWT survivrait à sa revocation —
    le navigateur continuerait de l'envoyer alors que le backend le
    rejetterait. Max-Age est donc calé sur `exp`, ce qui rend le cookie
    incapable de survivre a ce qu'il authentifie.
    """
    exp = claims.get("exp")
    if not isinstance(exp, (int, float)):
        return 0
    return max(0, int(exp - time.time()))


#: Message UNIQUE de refus (AGENTS.md §2 : « message générique »).
#:
#: Il couvre indistinctement un JSON malformé, un champ absent, un token
#: vide et une signature invalide. Un seul message ne permet pas de
#: distinguer les cas par sondage, et n'en dit pas plus long sur ce que
#: le validateur aurait entendu.
_GENERIC_REJECT = "Token invalide ou expiré"


@router.post(
    "/session",
    response_model=SessionStatus,
    # Le corps est lu à la main (voir create_session) : on réécrit donc la
    # schéma OpenAPI pour que la documentation reste juste.
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": SessionExchange.model_json_schema()}},
        }
    },
)
async def create_session(request: Request, response: Response) -> SessionStatus:
    """Vérifie le JWT puis le dépose en cookie HttpOnly.

    Le JWT n'est JAMAIS renvoyé dans le corps de la réponse : il ne
    fait qu'entrer pour ressortir en `Set-Cookie`, inaccessible au JS.

    POURQUOI LE CORPS EST LU À LA MAIN

    En laissant FastAPI valider `SessionExchange` en paramètre de route,
    un corps malformé renvoyait `422` avec le DÉTAIL du validateur
    Pydantic (`loc`, `msg`, `input`, `ctx`) — deux fois la structure
    attendue, donc un oracle sur ce que l'endpoint a tenté de lire.
    AGENTS.md §2 exige `401` + message générique sur une requête
    malformée : le refus doit être indiscernable, quelle que soit sa cause.

    Ici, TOUT ce que Pydantic refuse (JSON invalide, champ absent,
    token vide) devient le même `401 _GENERIC_REJECT`, exactement comme
    une signature invalide. Rien ne fuit, rien ne s'énumère.
    """
    try:
        payload = SessionExchange.model_validate_json(await request.body() or b"")
    except ValidationError:
        log_event(
            "AUTH_SESSION_MALFORMED",
            message=(
                "Corps /api/auth/session refuse par le validateur — "
                "rejet 401 generique, aucun detail renvoye"
            ),
        )
        raise HTTPException(status_code=401, detail=_GENERIC_REJECT)

    try:
        claims = verify_neon_token(payload.token)
    except HTTPException:
        # 503 explicite : la JWKS n'est pas configurée. On ne la masque
        # pas derrière un 401 — ce sont deux pannes différentes et
        # l'opérateur doit pouvoir les distinguer.
        raise
    except Exception as exc:
        # On journalise le TYPE de l'exception : le message « Token
        # invalide ou expiré » agrège trois causes très différentes
        # (clé absente du JWKS, audience divergente, signature fausse)
        # et rendait tout diagnostic aveugle.
        log_event(
            "AUTH_REJECT",
            message=(
                f"Session exchange rejected | err={log_safe(exc)} "
                f"type={type(exc).__name__}"
            ),
        )
        raise HTTPException(
            status_code=401,
            detail=_GENERIC_REJECT,
        )

    if not claims.get("sub"):
        raise HTTPException(status_code=401, detail="Token sans sub")

    max_age = _remaining_seconds(claims)
    if max_age <= 0:
        raise HTTPException(status_code=401, detail="Token expiré")

    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=payload.token,
        max_age=max_age,
        path=AUTH_COOKIE_PATH,
        httponly=True,
        secure=AUTH_COOKIE_SECURE,
        samesite=AUTH_COOKIE_SAMESITE,
    )
    return SessionStatus(authenticated=True, expires_in=max_age)


@router.get("/session", response_model=SessionStatus)
def read_session(request: Request) -> SessionStatus:
    """État de la session côté navigateur — jamais le token lui-même.

    Sert au diagnostic : « le cookie voyage-t-il ? » se répond ici sans
    ouvrir les DevTools.
    """
    token = extract_token(request)
    if not token:
        return SessionStatus(authenticated=False)
    try:
        claims = verify_neon_token(token)
    except Exception:
        # Un cookie invalide vaut « pas de session », pas une erreur :
        # cette route EST l'aperçu du « es-tu connecté ? ».
        return SessionStatus(authenticated=False)
    return SessionStatus(
        authenticated=True,
        expires_in=_remaining_seconds(claims),
    )


@router.delete("/session")
def delete_session(response: Response) -> SessionStatus:
    """Depose le cookie au logout.

    SANS cet appel, le cookie survivrait au signOut côté Neon : le
    backend continuerait d'accepter des requêtes pendant les 15
    minutes restantes — une deconnexion qui n'en serait pas une. Les
    drapeaux sont repasses a l'identique pour que le navigateur
    reconnaisse exactement le cookie a supprimer.
    """
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        path=AUTH_COOKIE_PATH,
        secure=AUTH_COOKIE_SECURE,
        httponly=True,
        samesite=AUTH_COOKIE_SAMESITE,
    )
    return SessionStatus(authenticated=False)


__all__ = ["router"]