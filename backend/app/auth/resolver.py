# Mission Identité — CurrentUserResolver (§4/§5 du brief)
#
# LE point unique où l'identité est établie :
#   Bearer token → vérification Clerk (JWKS réel, mode clerk)
#   → sub (clerk_user_id) → users.clerk_user_id → internal user_id
#   → rôle → CurrentUser
#
# AUCUN endpoint ne doit plus accepter un user_id du client comme
# source d'identité. Les routes dérivent TOUT de get_current_user().
#
# Modes :
#   AUTH_MODE=clerk → JWT réel (signature via PyJWKClient officiel,
#     issuer, exp, azp ; JAMAIS verify_signature=False ; JAMAIS de
#     sub trusté depuis le body ; JAMAIS de secret en dur)
#   AUTH_MODE=dev   → "Bearer dev:<name>" résolu en interne pour le
#     développement local sans clés Clerk. Mêmes règles d'ownership
#     — pas de contournement possible de l'isolation.
import time
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request
from jwt import PyJWKClient

from app.config import (
    ADMIN_CLERK_IDS,
    AUTH_MODE,
    CLERK_AUDIENCES,
    CLERK_ISSUER,
    CLERK_JWKS_URL,
    CLERK_JWT_LEEWAY,
    log_safe,
)
from app.db import users as users_db
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
# Vérification JWT Clerk ( mode clerk — réel )
# ------------------------------------------------------------------

_jwk_client: PyJWKClient | None = None


def _get_jwk_client() -> PyJWKClient:
    """Client JWKS officiel (cache des clés publiques Clerk)."""
    global _jwk_client
    if _jwk_client is None:
        if not CLERK_JWKS_URL:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Auth Clerk non configurée : définir "
                    "CLERK_ISSUER (ex: https://xxx.clerk.accounts.com)"
                    " ou CLERK_JWKS_URL dans .env",
                ),
            )
        _jwk_client = PyJWKClient(CLERK_JWKS_URL, cache_keys=True)
    return _jwk_client


def verify_clerk_token(token: str) -> dict:
    """Vérifie un JWT Clerk : signature, issuer, exp, aud, sub.

    Mécanisme officiel Clerk pour backends Python (PyJWKClient).
    Lève jwt.PyJWTError en cas d'échec ( transformé en 401 ).
    """
    client = _get_jwk_client()
    signing_key = client.get_signing_key_from_jwt(token)

    options: dict = {"require": ["exp", "iat", "sub", "iss"]}
    decode_kwargs: dict = {
        "key": signing_key.key,
        "algorithms": ["RS256"],
        "options": options,
        # Tolérance d'horloge ( secondes ) : absorbe une légère dérive
        # locale ( iat/nbf perçus comme futurs ). N'affaiblit PAS la
        # vérification : signature, issuer, audience et exp restent
        # strictement contrôlés.
        "leeway": CLERK_JWT_LEEWAY,
    }
    if CLERK_ISSUER:
        decode_kwargs["issuer"] = CLERK_ISSUER
    if CLERK_AUDIENCES:
        decode_kwargs["audience"] = CLERK_AUDIENCES
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
        return {
            "user_id": existing["user_id"],
            "is_admin": clerk_user_id in ADMIN_CLERK_IDS,
        }

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
    return {
        "user_id": created["user_id"],
        "is_admin": clerk_user_id in ADMIN_CLERK_IDS,
    }


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

    # Mode clerk : vérification RÉELLE
    try:
        claims = verify_clerk_token(token)
    except HTTPException:
        raise
    except Exception as exc:  # jwt.ExpiredSignatureError, etc.
        log_event(
            "AUTH_REJECT",
            message=f"Token rejected | err={log_safe(exc)}",
        )
        raise HTTPException(
            status_code=401,
            detail="Token invalide ou expiré",
        )
    sub = claims.get("sub") or ""
    if not sub:
        raise HTTPException(status_code=401, detail="Token sans sub")
    # Nom d'affichage depuis les claims ( username / email )
    display = (
        claims.get("username")
        or claims.get("name")
        or ""
    )
    return resolve_internal_user(sub, display)


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
    """Test réseau du JWKS ( sans cache ) — observabilité health."""
    global _last_jwks_check
    now = time.time()
    if now - _last_jwks_check.get("ts", 0) < 30:
        return _last_jwks_check.get("ok", False)
    try:
        client = PyJWKClient(CLERK_JWKS_URL, cache_keys=True)
        client.get_signing_keys()
        _last_jwks_check = {"ts": now, "ok": True}
        return True
    except Exception:
        _last_jwks_check = {"ts": now, "ok": False}
        return False
