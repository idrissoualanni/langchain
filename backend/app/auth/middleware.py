# Mission Identité — middleware d'AUTHENTIFICATION global (user + admin).
#
# Défense en DEUX COUCHES :
#   Couche 1 (ce middleware) : barrière grossière au niveau HTTP.
#     - toute route /api/** (hors liste publique) exige une PREUVE
#       d'identité valide ( Bearer token résolu par CurrentUserResolver )
#     - toute route /api/admin/** et /ws/logs exige un ADMIN (403)
#     → un endpoint oublié sans Depends() n'est plus une brèche.
#   Couche 2 (get_current_user / require_admin dans les routes) :
#     reste LA source de l'identité applicative (ownership, user_id
#     interne). Le middleware ne la remplace pas — il la complète.
#
# Résolution mutualisée : le middleware consomme le token AVANT la
# route et dépose le CurrentUser sur request.state.user ; get_current_user
# lit ce dépôt ( même requête, jamais ressassé ni truste du client ).
#
# Fail-SAFE : si AUTH_MODE passe à "neon" sans que JWKS soit
# configuré, TOUTES les routes protégées répondent 503 — jamais un
# contournement ouvert. En mode dev, le pipeline token→user existe
# déjà ("dev:<id|name>") : le middleware est actif, non neutre.
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from app.auth.resolver import _resolve_from_token
from app.config import AUTH_MODE, NEON_AUTH_JWKS_URL
from app.logging.events import log_event

# Routes /api publiques — authentification non exigée.
#   health* : monitoring infra (les badges admin reposent dessus)
PUBLIC_API_PREFIXES = ("/api/health",)
PUBLIC_API_EXACT: set[str] = set()


def _is_public(path: str) -> bool:
    if path.startswith(PUBLIC_API_PREFIXES):
        return True
    return path in PUBLIC_API_EXACT


def _requires_admin(path: str) -> bool:
    # /api/admin/** (dashboard, modèles, savoir, observabilité) + flux
    # temps réel des logs techniques (§22 : réservés ADMIN).
    return path.startswith("/api/admin") or path == "/ws/logs"


class AuthGateMiddleware(BaseHTTPMiddleware):
    """Barrière d'authentification HTTP : user pour /api/**, admin pour
    /api/admin/** et /ws/logs. 401 sans preuve, 403 si rôle insuffisant."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        # Cache anti-DDoS : la vérif de config (réseau) n'est testée
        # qu'au plus une fois toutes les 30 s.
        self._config_checked_at = 0.0
        self._config_ok = False

    def _auth_configured(self) -> bool:
        if AUTH_MODE == "dev":
            return True
        if AUTH_MODE == "neon":
            return bool(NEON_AUTH_JWKS_URL)
        # Mode inconnu ( ex: ancienne config "clerk" ) → fail-closed.
        return False

    def _config_ready_or_response(self) -> JSONResponse | None:
        if time.time() - self._config_checked_at >= 30:
            self._config_checked_at = time.time()
            self._config_ok = self._auth_configured()
        if self._config_ok:
            return None
        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    "Authentification indisponible : JWKS non configuré "
                    f"(AUTH_MODE={AUTH_MODE})"
                ),
                "code": "auth_unavailable",
                "error": True,
            },
        )

    async def dispatch(self, request, call_next):
        path = request.url.path

        # 1. Tout ce qui n'est pas une route API protégée passe
        #    ( docs, root, statiques — CORS géré en amont ).
        if not (path.startswith("/api") or path == "/ws/logs"):
            return await call_next(request)
        if _is_public(path):
            return await call_next(request)

        # 2. Fail-safe : config HS → 503, jamais un accès ouvert.
        unavailable = self._config_ready_or_response()
        if unavailable is not None:
            return unavailable

        # 3. Preuve d'identité : Bearer header ( EventSource/WebSocket
        #    portent ?auth=<token> — même mécanisme que /api/events ).
        header = request.headers.get("authorization") or ""
        token = (
            header[7:].strip()
            if header.lower().startswith("bearer ")
            else (request.query_params.get("auth") or "").strip()
        )
        if not token:
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Authentification requise (Bearer token)",
                    "code": "unauthorized",
                    "error": True,
                },
            )

        try:
            current = _resolve_from_token(token)
        except Exception as exc:  # noqa: BLE001 — HTTPException ou autre
            log_event(
                "AUTH_REJECT",
                message=f"Middleware gate rejected | path={path}",
            )
            status = getattr(exc, "status_code", 401)
            detail = getattr(exc, "detail", "Token invalide ou expiré")
            return JSONResponse(
                status_code=status if status in (401, 503) else 401,
                content={"detail": detail, "code": "unauthorized", "error": True},
            )

        # 4. Dépôt pour get_current_user ( résolution unique par requête ).
        request.state.user = current

        # 5. Exigence ADMIN sur les surfaces d'administration.
        if _requires_admin(path) and not current.is_admin:
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "Réservé aux administrateurs",
                    "code": "forbidden",
                    "error": True,
                },
            )

        return await call_next(request)
