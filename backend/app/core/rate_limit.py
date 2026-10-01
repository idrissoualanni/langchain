# Rate Limiting — slowapi avec backend Redis ( ADR-006bis ).
#
# Global : 30 req/min par utilisateur ( identifié via CurrentUser.user_id ).
# Endpoints sensibles : limites plus strictes ( chat, upload, auth ).
# Fallback : si Redis indisponible → log + pas de blocage ( fail-open ).
#
# Pourquoi slowapi : standard FastAPI, stockage Redis natif, décorateurs
# @limiter.limit() sur routes, clés flexibles ( user_id, IP, custom ).
import os
from typing import Callable

from fastapi import Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.auth.resolver import CurrentUser, get_current_user
from app.infrastructure.cache.factory import get_cache
from app.logging.events import log_event

# ----------------------------------------------------------------------
# Key functions — déterminent l'identité pour le rate limiting
# ----------------------------------------------------------------------


def _get_user_id_from_request(request: Request) -> str:
    """
    Extrait l'user_id depuis CurrentUser ( injecté par get_current_user ).
    Fallback sur IP si pas d'utilisateur ( ex. health, docs ).
    """
    # CurrentUser est attaché à request.state.current_user par la dépendance
    # dans les routes protégées. Si absent, on tente l'IP.
    current_user: CurrentUser | None = getattr(request.state, "current_user", None)
    if current_user and current_user.user_id:
        return f"user:{current_user.user_id}"
    # Fallback IP pour endpoints non-authentifiés
    return f"ip:{get_remote_address(request)}"


def _get_admin_key(request: Request) -> str:
    """Clé pour endpoints admin — par user_id admin."""
    current_user: CurrentUser | None = getattr(request.state, "current_user", None)
    if current_user and current_user.user_id:
        return f"admin:{current_user.user_id}"
    return f"admin:ip:{get_remote_address(request)}"


# ----------------------------------------------------------------------
# Limiter instance — backend Redis si REDIS_URL, sinon mémoire ( slowapi défaut )
# ----------------------------------------------------------------------


def _get_storage_uri() -> str | None:
    """Retourne REDIS_URL si dispo, sinon None ( slowapi utilisera son stockage mémoire )."""
    url = os.getenv("REDIS_URL", "").strip()
    return url if url else None


# Instance principale — clé par user_id ( via _get_user_id_from_request )
limiter = Limiter(
    key_func=_get_user_id_from_request,
    storage_uri=_get_storage_uri(),
    default_limits=["30/minute"],  # Global : 30 req/min/user
    headers_enabled=True,  # Ajoute X-RateLimit-* aux réponses
)


# ----------------------------------------------------------------------
# Décorateurs prêts à l'emploi pour endpoints sensibles
# ----------------------------------------------------------------------


# Chat / streaming — plus restrictif ( coûteux en LLM )
chat_limit = limiter.limit("20/minute")

# Upload fichiers — très restrictif ( I/O + vectorisation )
upload_limit = limiter.limit("10/minute")

# Auth / login — anti brute-force
auth_limit = limiter.limit("5/minute")

# Admin — plus permissif mais tracé
admin_limit = limiter.limit("60/minute")

# Health / docs — pas de limite ( ou très large )
health_limit = limiter.limit("300/minute")


# ----------------------------------------------------------------------
# Exception handler — réponse 429 cohérente avec AppError
# ----------------------------------------------------------------------


def _retry_after_seconds(exc: RateLimitExceeded) -> int:
    """Secondes avant la prochaine fenêtre.

    RateLimitExceeded ( slowapi ) n'expose PAS retry_after : il dérive
    de HTTPException avec `.limit` ( objet slowapi.wrappers.Limit ) qui
    porte la fenêtre (`per` secondes pour « 30/minute » → 60 ). Repli 60 s.
    """
    limit = getattr(exc, "limit", None)
    per = getattr(limit, "per", None)
    if isinstance(per, (int, float)) and per > 0:
        return int(per)
    return 60


def _limit_label(exc: RateLimitExceeded) -> str:
    """Libellé lisible de la limite ( ex. « 30 per 1 minute » )."""
    inner = getattr(getattr(exc, "limit", None), "limit", None)
    return str(inner) if inner is not None else str(getattr(exc, "detail", exc))


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Handler 429 formaté comme nos AppError ( code, detail ).

    Chemin ROUTE : l'exception levée par @limiter.limit( ... ) traverse
    le router, ce handler est appelé par ExceptionMiddleware.
    """
    retry_after = _retry_after_seconds(exc)
    log_event(
        "RATE_LIMIT_EXCEEDED",
        level="WARNING",
        message=f"Rate limit exceeded: {exc.detail}",
        extra={"retry_after": retry_after, "limit": _limit_label(exc)},
    )
    return _rate_limit_exceeded_handler(request, exc)


# ----------------------------------------------------------------------
# Dépendance pour injecter CurrentUser dans request.state
# ( nécessaire pour que _get_user_id_from_request fonctionne )
# ----------------------------------------------------------------------


async def inject_current_user(request: Request, current: CurrentUser = Depends(get_current_user)):
    """Dépendance à ajouter sur les routes protégées pour peupler request.state.current_user."""
    request.state.current_user = current
    return current


# ----------------------------------------------------------------------
# Helper pour initialiser le rate limiting sur l'app FastAPI
# ----------------------------------------------------------------------


def _build_429(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Réponse 429 avec headers X-RateLimit-* et Retry-After.

    Construite à la main car l'exception levée dans le MIDDLEWARE ne
    traverse pas le router : `app.add_exception_handler` ne la capte
    pas. On doit donc renvoyer la réponse directement ici.
    """
    retry_after = _retry_after_seconds(exc)
    # Trace l'événement ( observabilité — même chemin que le handler route )
    log_event(
        "RATE_LIMIT_EXCEEDED",
        level="WARNING",
        message=f"Rate limit exceeded: {exc.detail}",
        extra={"retry_after": retry_after, "limit": _limit_label(exc)},
    )
    response = JSONResponse(
        {
            "error": f"Rate limit exceeded: {exc.detail}",
            "code": "rate_limit_exceeded",
            "retry_after": retry_after,
        },
        status_code=429,
        headers={"Retry-After": str(retry_after)},
    )
    # Headers X-RateLimit-Limit / Remaining / Reset ( si stats dispo )
    current_limit = getattr(request.state, "view_rate_limit", None)
    if current_limit is not None:
        try:
            response = limiter._inject_headers(response, current_limit)
        except Exception:  # pragma: no cover — Redis down, header optionnel
            pass
    return response


async def _global_rate_limit_middleware(request: Request, call_next):
    """
    Middleware HTTP global — applique les default_limits ( 30/min ) à TOUTES
    les routes, AVANT d'entrer dans le router.

    Le décorateur @limiter.limit() sur une route ajoute SA propre limite
    ( ex. 20/min pour /api/chat ) : les deux compteurs sont indépendants
    et s'additionnent ( un appel consomme 1 unité globale + 1 unité route ).

    POURQUOI pas via app.add_exception_handler : une exception levée dans
    un middleware est captée par ServerErrorMiddleware ( qui la relance ),
    pas par ExceptionMiddleware ( qui dispatche les handlers enregistrés ).
    D'où le try/except ici + JSONResponse construite à la main.
    """
    # Préflight CORS : ne pas compter les requêtes OPTIONS
    if request.method == "OPTIONS":
        return await call_next(request)

    try:
        # Mode middleware : applique default_limits ( 30/minute ) à la route
        limiter._check_request_limit(request, endpoint_func=None, in_middleware=True)
    except RateLimitExceeded as exc:
        # 429 direct — l'exception ne remontera pas vers le handler global
        return _build_429(request, exc)

    response = await call_next(request)

    # Header X-RateLimit-* avec la limite effective ( route si décorée,
    # sinon globale ) — stockée par _evaluate_limits dans request.state
    current_limit = getattr(request.state, "view_rate_limit", None)
    if current_limit is not None:
        try:
            response = limiter._inject_headers(response, current_limit)
        except Exception:  # pragma: no cover — Redis down, header optionnel
            pass
    return response


def setup_rate_limiting(app) -> None:
    """
    À appeler dans main.py après création de l'app :
        from app.core.rate_limit import setup_rate_limiting
        setup_rate_limiting(app)

    Ajoute :
    - middleware HTTP global ( default_limits 30/min sur TOUTES les routes )
    - exception handler 429 ( routes décorées @limiter.limit )
    - headers X-RateLimit-* sur toutes les réponses
    """
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    # Middleware global — AJOUTÉ APRÈS CORS dans la pile ( CORS reste
    # le plus externe, il traite OPTIONS en premier )
    app.middleware("http")(_global_rate_limit_middleware)


# ----------------------------------------------------------------------
# Export
# ----------------------------------------------------------------------

__all__ = [
    "limiter",
    "chat_limit",
    "upload_limit",
    "auth_limit",
    "admin_limit",
    "health_limit",
    "setup_rate_limiting",
    "inject_current_user",
]