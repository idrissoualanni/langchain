# Mission Identité — CurrentUserResolver (§4/§5 du brief)
#
# LE point unique où l'identité est établie :
#   Bearer token → vérification Neon Auth (JWKS réel, mode neon)
#   → sub (identifiant externe) → users.clerk_user_id → user_id interne
#   → rôle → CurrentUser
#
# AUCUN endpoint ne doit plus accepter un user_id du client comme
# source d'identité. Les routes dérivent TOUT de get_current_user().
#
# Modes :
#   AUTH_MODE=neon → JWT réel EdDSA (signature via PyJWKClient officiel,
#     exp, sub ; JAMAIS verify_signature=False ; JAMAIS de sub trusté
#     depuis le body ; JAMAIS de secret en dur)
#   AUTH_MODE=dev  → "Bearer dev:<name>" résolu en interne pour le
#     développement local sans clés externes. Mêmes règles d'ownership
#     — pas de contournement possible de l'isolation.
#
# ⚠️ FAIL-CLOSED : un AUTH_MODE inconnu ÉCHOIT en 503. Il ne doit
# JAMAIS exister de chemin par lequel _resolve_from_token() retourne
# None sans lever — une dépendance FastAPI qui reçoit None casse
# l'isolation silencieusement.
import time
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request
from jwt import PyJWKClient

from app.config import (
    ADMIN_CLERK_IDS,
    AUTH_MODE,
    JWT_LEEWAY,
    NEON_AUTH_JWKS_URL,
    NEON_AUTH_BASE_URL,
    log_safe,
)
from app.infrastructure.database import users as users_db
from app.logging.events import log_event


@dataclass
class CurrentUser:
    """Utilisateur courant RÉSOLU (jamais déclaré par le client)."""

    clerk_user_id: str
    user_id: str          # internal UUID — clé de TOUT le stockage
    name: str
    role: str             # "user" | "admin"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


# ------------------------------------------------------------------
# Vérification JWT Neon Managed Better Auth ( mode neon — réel )
# ------------------------------------------------------------------
# Neon Auth ( Better Auth ) signe ses JWT avec les clés publiques du
# well-known endpoint du projet Neon, via PyJWKClient :
#   sub  → identifiant utilisateur Neon ( stocké dans la colonne
#          users.clerk_user_id, nom historique conservé )
#   email/name → nom d'affichage pour le provisioning interne

_neon_jwk_client: PyJWKClient | None = None


def _get_neon_jwk_client() -> PyJWKClient:
    """Client JWKS officiel Neon Auth ( cache des clés publiques )."""
    global _neon_jwk_client
    if _neon_jwk_client is None:
        if not NEON_AUTH_JWKS_URL:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Auth Neon non configurée : définir "
                    "NEON_AUTH_JWKS_URL dans .env ( well-known "
                    "endpoint du projet Neon Auth )",
                ),
            )
        _neon_jwk_client = PyJWKClient(
            NEON_AUTH_JWKS_URL, cache_keys=True
        )
    return _neon_jwk_client


def verify_neon_token(token: str) -> dict:
    """Vérifie un JWT Neon Auth : signature, exp, sub.

    Pas d'issuer ni d'audience codés en dur ( Neon/Better Auth ne
    fournit pas de vérification d'issuer côté backend — la signature
    JWKS + l'exp suffisent ; la clé publique ne provient QUE du
    well-known Neon ).

    ATTENTION : Neon Auth ( Better Auth ) signe en EdDSA / Ed25519
    ( clé OKP ), PAS en RS256. PyJWT supporte EdDSA dès que
    `cryptography` est installé ( requirements.txt ).
    Lève jwt.PyJWTError en cas d'échec ( transformé en 401 ).
    """
    client = _get_neon_jwk_client()
    signing_key = client.get_signing_key_from_jwt(token)

    options: dict = {"require": ["exp", "iat", "sub"]}
    decode_kwargs: dict = {
        "key": signing_key.key,
        # Ed25519 ( OKP ) — signature EdDSA.
        "algorithms": ["EdDSA"],
        "options": options,
        # Tolérance d'horloge ( secondes ) — absorbe la dérive locale
        # des postes ; n'affaiblit PAS la vérification.
        "leeway": JWT_LEEWAY,
    }
    # Better Auth pose un claim aud ( = URL du service Neon Auth ).
    # PyJWT rejette par défaut tout token portant un aud non vérifié
    # ( InvalidAudienceError ) → on déclare l'audience attendue dès que
    # la base URL est configurée, sinon on déspose juste la vérif aud.
    if NEON_AUTH_BASE_URL:
        decode_kwargs["audience"] = NEON_AUTH_BASE_URL
    else:
        options["verify_aud"] = False
    return jwt.decode(token, **decode_kwargs)


# ------------------------------------------------------------------
# Provisioning : Clerk user → user interne (§6/§7)
# ------------------------------------------------------------------

def resolve_internal_user(
    clerk_user_id: str, display_name: str
) -> CurrentUser:
    """Mappe clerk_user_id → user interne, avec provisioning.

    - login 1 : aucun user avec ce clerk_user_id → provisionnement
      (nouvel UUID interne, ENREGISTRÉ avec son clerk_user_id)
    - logins suivants : RETROUVE LE MÊME user interne ( jamais de
      nouvel UUID à chaque connexion )
    - les users existants sans clerk_user_id ne sont JAMAIS
      rattachés arbitrairement (§7) — ils restent intacts.
    """
    existing = users_db.get_user_by_clerk_id(clerk_user_id)
    if existing is not None:
        role = (
            "admin"
            if clerk_user_id in ADMIN_CLERK_IDS
            else _role_of(existing)
        )
        return CurrentUser(
            clerk_user_id=clerk_user_id,
            user_id=existing["user_id"],
            name=existing.get("name") or display_name or "Utilisateur",
            role=role,
        )

    # Provisioning du premier login
    created = users_db.create_user(
        display_name or "Utilisateur",
        clerk_user_id=clerk_user_id,
        role=(
            "admin" if clerk_user_id in ADMIN_CLERK_IDS else "user"
        ),
    )
    log_event(
        "AUTH_PROVISION",
        message=f"User provisioned from Clerk | name={display_name}",
        user_id=created["user_id"],
    )
    return CurrentUser(
        clerk_user_id=clerk_user_id,
        user_id=created["user_id"],
        name=created.get("name") or display_name or "Utilisateur",
        role=(
            "admin" if clerk_user_id in ADMIN_CLERK_IDS else "user"
        ),
    )


def _role_of(user_row: dict) -> str:
    """Rôle stocké en base (colonne role, défaut 'user')."""
    return user_row.get("role") or "user"


# ------------------------------------------------------------------
# Dépendances FastAPI (§4/§9)
# ------------------------------------------------------------------

def _extract_bearer(request: Request) -> str:
    """Extrait le Bearer token — 401 sinon."""
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authentification requise (Bearer token)",
        )
    token = header[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Token manquant")
    return token


def _resolve_from_token(token: str) -> CurrentUser:
    """Token vérifié → CurrentUser (selon AUTH_MODE)."""
    if AUTH_MODE == "dev":
        # Mode dev : "dev:<internal_user_id>" OU "dev:<name>".
        # UUID → user interne existant (sessions de test des suites
        # de régression) ; name → provisioning local. L'identité
        # vient TOUJOURS du token, jamais du body.
        if not token.startswith("dev:"):
            raise HTTPException(
                status_code=401,
                detail="Mode dev : token attendu 'dev:<id|name>'",
            )
        ident = token[4:].strip()
        if not ident:
            raise HTTPException(401, detail="Token dev vide")
        # UUID interne existant ?
        row = users_db.get_user(ident)
        if row is not None:
            return CurrentUser(
                clerk_user_id=row.get("clerk_user_id")
                or f"dev-{row['user_id'][:8]}",
                user_id=row["user_id"],
                name=row["name"],
                role=_role_of(row),
            )
        # admin flag config : ADMIN_CLERK_IDS "dev-admin"
        if ident in ADMIN_CLERK_IDS:
            return resolve_internal_user(
                f"dev-{ident}", ident
            )
        return resolve_internal_user(
            f"dev-{ident[:24]}", ident
        )

    # Mode neon : vérification RÉELLE des JWT Neon Managed Better Auth
    # ( même pipeline que clerk : JWKS → sub → user interne ). Le sub
    # Neon joue le rôle du clerk_user_id : resolve_internal_user le
    # mappe en user interne ( provisioning au premier login ).
    if AUTH_MODE == "neon":
        try:
            claims = verify_neon_token(token)
        except HTTPException:
            raise
        except Exception as exc:  # jwt.ExpiredSignatureError, etc.
            log_event(
                "AUTH_REJECT",
                message=(
                    f"Token rejected | mode=neon err={log_safe(exc)}"
                ),
            )
            raise HTTPException(
                status_code=401,
                detail="Token invalide ou expiré",
            )
        sub = claims.get("sub") or ""
        if not sub:
            raise HTTPException(
                status_code=401, detail="Token sans sub"
            )
        # Nom d'affichage depuis les claims Neon/Better Auth
        # ( email prioritaire, puis name ).
        display = (
            claims.get("email")
            or claims.get("name")
            or claims.get("username")
            or ""
        )
        return resolve_internal_user(sub, display)

    # ⚠️ FAIL-CLOSED : AUTH_MODE inconnu ou mal orthographié.
    # AVANT ce garde-fou, la fonction tombait hors de tout `if` et
    # retournait None — une dépendance FastAPI recevant None casse
    # l'isolation SILENCIEUSEMENT ( pas de 401, pas de log ).
    # Toute valeur hors {neon, dev} est donc un défaut de config :
    # 503 explicite, jamais None. AUTH_MODE n'est pas secret
    # ( déjà renvoyé par GET /api/health/auth ).
    log_event(
        "AUTH_REJECT",
        message=f"AUTH_MODE inconnu | mode={AUTH_MODE!r}",
    )
    raise HTTPException(
        status_code=503,
        detail=f"Mode d'authentification non supporté : {AUTH_MODE!r}",
    )


def get_current_user(
    request: Request,
) -> CurrentUser:
    """DÉPENDANCE CENTRALE — l'identité vient UNIQUEMENT d'ici."""
    token = _extract_bearer(request)
    return _resolve_from_token(token)


def require_admin(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """401 si non authentifié, 403 si role=user, sinon admin."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Réservé aux administrateurs",
        )
    return current_user


def optional_current_user(
    request: Request,
) -> CurrentUser | None:
    """User courant si token présent et valide — None sinon.

    Pour les routes publiques qui s'enrichissent si authentifiées
    ( ex : /api/health reste public ).
    """
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        return None
    try:
        token = header[7:].strip()
        if not token:
            return None
        return _resolve_from_token(token)
    except HTTPException:
        return None


# ------------------------------------------------------------------
# Health de l'auth ( observabilité )
# ------------------------------------------------------------------

def auth_mode() -> str:
    return AUTH_MODE


_last_jwks_check: dict = {}


def jwks_reachable() -> bool:
    """Test réseau du JWKS ( sans cache ) — observabilité health.

    Neon Auth est le SEUL fournisseur d'identité : son well-known est
    testé dans tous les modes, y compris dev — en dev on observe la
    joignabilité de la cible de PRODUCTION, pas d'unJWKS local.
    """
    global _last_jwks_check
    now = time.time()
    if now - _last_jwks_check.get("ts", 0) < 30:
        return _last_jwks_check.get("ok", False)
    jwks_url = NEON_AUTH_JWKS_URL
    if not jwks_url:
        _last_jwks_check = {"ts": now, "ok": False}
        return False
    try:
        client = PyJWKClient(jwks_url, cache_keys=True)
        client.get_signing_keys()
        _last_jwks_check = {"ts": now, "ok": True}
        return True
    except Exception:
        _last_jwks_check = {"ts": now, "ok": False}
        return False
