# FastAPI — Agent Control Center backend
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.graph.main import get_agent
from app.api import (
    activity,
    agent_memory,
    auth,
    chat,
    context,
    documents,
    health,
    learning,
    livekit,
    logs,
    memory,
    models,
    storage,
    subjects,
    threads,
    users,
)
from app.api.user import memory as user_memory
from app.features.transcription.api import router as transcription_router
from app.api.admin import (
    models_router as admin_models_router,
    knowledge_router as admin_knowledge_router,
    subjects_router as admin_subjects_router,
    monitoring_router as admin_monitoring_router,
    observability_router as admin_observability_router,
    dashboard_router as admin_dashboard_router,
    users_router as admin_users_router,
    mcp_router as admin_mcp_router,
    providers_router as admin_providers_router,
)
from app.infrastructure.database.connections import init_db
from app.infrastructure.database.persistence import (
    init_persistence,
    is_postgres_persistence,
)
from app.infrastructure.database.schema import init_schema
from app.logging.events import log_event, setup_logging
from app.logging.sse import sse_events
from app.config import ALLOWED_ORIGINS
from app.core.rate_limit import setup_rate_limiting, limiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup : logging + DB + agent warm-up + loop registration.
    setup_logging()

    # Sentry initialization
    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        integrations=[FastApiIntegration()],
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )
    init_db()
    # Checkpointer + store LangGraph sur Neon (PostgreSQL) — SQLite
    # retiré. AVANT l'agent : le graphe demande son checkpointer à
    # l'initialisation.
    init_persistence()
    # Tables applicatives Neon : binaires (BYTEA), vidéos, MCP, knowledge.
    # Idempotent — ne touche jamais aux données existantes.
    init_schema()

    # Monitoring admin : thread écrivain qui persiste log_event dans
    # agent_events ( Neon ) — file bornée, jamais bloquant.
    from app.logging.events import start_event_persistence

    start_event_persistence()

    # Corpus knowledge : il vit DÉSORMAIS dans Neon ( knowledge_sections,
    # vectorisé ) — plus aucun fichier Markdown dans le dépôt, donc
    # plus d'indexation au démarrage. La réindexation passe par la
    # migration initiale ( hors serveur ).

    # Enregistre la loop pour que log_event (appelé depuis des threads
    # executor pendant les runs agent) puisse publier sur le bus SSE
    # de façon thread-safe.
    from app.logging.events import set_main_loop

    set_main_loop(asyncio.get_running_loop())

    log_event("SERVER_START", message="Backend starting")

    try:
        get_agent()
        log_event(
            "AGENT_READY",
            message=(
                "LangGraph agent initialized — persistence="
                + ("PostgreSQL (Neon)" if is_postgres_persistence()
                   else "SQLite")
            ),
        )
    except Exception as exc:
        log_event(
            "AGENT_INIT_ERROR",
            level="ERROR",
            message=f"Agent init failed: {exc}",
        )

    yield

    from app.observability.langfuse import shutdown_langfuse

    shutdown_langfuse()  # vide la file d'export Langfuse (jamais levant)

    # Sessions MCP (inspector admin) — sans ça, les sous-processus
    # stdio survivent au redémarrage du serveur.
    # Ne leve JAMAIS : on ne bloque pas la sortie du process.
    from app.infrastructure.mcp.session import close_all_sessions

    await close_all_sessions()

    log_event("SERVER_STOP", message="Backend shutting down")


app = FastAPI(
    title="Agent Control Center API",
    version="1.0.0",
    lifespan=lifespan,
)

# ----------------------------------------------------------------------
# Mission Sécurité — CSRF + en-têtes
# ----------------------------------------------------------------------
# ORDRE DES MIDDLEWARES : Starlette empile en LIFO — le DERNIER
# `add_middleware` ajouté est le PLUS EXTERNE. On déclare donc ces deux
# lavas AVANT le CORS pour que le CORS reste au plus haut de l'pile :
# ainsi un 403 anti-CSRF passe quand meme par le CORS et porte les
# `Access-Control-*`, donc le front peut le lire au lieu de voir une
# erreur réseau opaque.
#
# Triche assumee : une reponse de PREFLIGHT (OPTIONS) est traitee
# directement par CORSMiddleware, sans descendre jusqu'ici. Elle ne
# sera donc pas decoratee de nos en-tetes. C'est sans consequence —
# un preflight ne contient aucune donnee et n'est jamais rendu.
SECURITY_HEADERS = {
    # HSTS : force le HTTPS pendant 1 an, sous-domaines inclus.
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    # Empeche le navigateur de deviner un type MIME different de
    # celui annonce (une "image" servie en HTML devient un script).
    "X-Content-Type-Options": "nosniff",
    # Ne laisse fuiter le chemin complet vers les sites tiers.
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # Le micro et la camera ne sont autorises que pour nous-memes.
    # Rappel : LiveKit a besoin du micro → on ne peut pas les interdire.
    "Permissions-Policy": (
        "camera=(self), microphone=(self), geolocation=()"
    ),
    # Defense en profondeur : la CSP porte aussi frame-ancestors, mais
    # ce header couvre les clients qui ne lisent pas la CSP.
    "X-Frame-Options": "DENY",
}

# Methodes qui modifient une donnee — les seules que le CSRF menace.
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def enforce_origin(request: Request, call_next):
    """Rejette les requetes mutantes venues d'un site non autorisé.

    Le cookie de session est `SameSite=None` — c'est le prix à payer
    pour que le front Vercel atteigne l'API Render (cf. auth.py). Mais
    `SameSite=None` supprime precisement la protection que `Lax`
    apportait : n'importe quel site peut désormais poster une requete
    au NAVIGATEUR de l'utilisateur, qui part avec son cookie. Sans ce
    garde-fou, la lecture seule d'une page tierce suffirait à agir en
    son nom.

    On separe donc `Lax` (confort) de `Origin` (securite) : meme
    domaine pour le cookie, liste blanche explicite pour l'Origine.

    Le controle porte sur `Origin` seul. Les navigateurs l'envoient
    systematiquement sur POST/PUT/PATCH/DELETE, y compris cross-site :
    une attaque CSRF depuis une page tierre fournit donc TOUJOURS un
    Origin, et il est rejete. Une requete sans Origin n'est pas une
    attaque : elle vient d'un client non-navigateur (curl, CLI, test
    LiveKit), qui ne peut pas detourner le cookie de quelqu'un d'autre.
    `Referer` n'est donc pas necessaire — et l'analyser en repli
    n'ajouterait qu'un second parseur, fragile, a maintenir.
    """
    if request.method in MUTATING_METHODS:
        origin = request.headers.get("origin")
        if origin and origin not in ALLOWED_ORIGINS:
            return JSONResponse(
                {"detail": "Origine non autorisée"},
                status_code=403,
            )
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Pose les en-tetes de securite sur TOUTES les reponses."""
    response = await call_next(request)
    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    return response


# CORS — frontend (dev Vite local + domaines Vercel via env)
# allow_credentials=True est coherent avec les cookies : c'est
# exactement ce qui rend le cookie `SameSite=None` utilisable, et c'est
# aussi pourquoi ALLOWED_ORIGINS ne doit JAMAIS contenir `*` (le
# navigateur le refuserait avec les credentials).
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting — global 30 req/min/user + limites par endpoint sensible.
# Backend Redis ( REDIS_URL ) si dispo, sinon mémoire. 429 formaté
# comme les AppError {code, detail}.
setup_rate_limiting(app)

# Routes API
app.include_router(users.router)
app.include_router(threads.router)
app.include_router(chat.router)
app.include_router(models.router)
app.include_router(memory.router)
app.include_router(logs.router)
app.include_router(health.router)
app.include_router(subjects.router)
app.include_router(context.router)
app.include_router(learning.router)
app.include_router(activity.router)
app.include_router(documents.router)
app.include_router(storage.router)
app.include_router(livekit.router)
app.include_router(auth.router)
app.include_router(agent_memory.router)
app.include_router(user_memory.router)
app.include_router(transcription_router)

# Admin API — Model/Knowledge/Observability/Dashboard management (secured)
# Les routers models/knowledge portent déjà leur préfixe /api/admin/...
# complet ; observability/dashboard utilisent /observability et /dashboard.
app.include_router(admin_models_router, tags=["admin-models"])
app.include_router(admin_knowledge_router, tags=["admin-knowledge"])
app.include_router(admin_subjects_router, tags=["admin-subjects"])
app.include_router(admin_monitoring_router, tags=["admin-monitoring"])
app.include_router(admin_observability_router, prefix="/api/admin", tags=["admin-observability"])
app.include_router(admin_dashboard_router, prefix="/api/admin", tags=["admin-dashboard"])
app.include_router(admin_users_router, tags=["admin-users"])
app.include_router(admin_mcp_router, prefix="/api/admin", tags=["admin-mcp"])
app.include_router(admin_providers_router, prefix="/api/admin", tags=["admin-providers"])

# SSE — événements agent temps réel
app.add_api_route(
    "/api/events",
    sse_events,
    methods=["GET"],
)


# ----------------------------------------------------------------------
# Error taxonomy (§63) — la hiérarchie AppError (core/exceptions.py)
# est convertie en réponses HTTP COHÉRENTES {code, detail}. Sans ces
# handlers, une AppError remonterait en 500 générique et le frontend
# ne pourrait pas distinguer les familles d'erreur (routing, retrieval,
# model, memory…). Le message renvoyé est sanitized via .detail()
# (pas de secret, cause technique tronquée à 300 c.).
# ----------------------------------------------------------------------
from app.core.exceptions import AppError


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    log_event(
        "APP_ERROR",
        level="ERROR",
        message=exc.detail(),
        extra={"code": exc.code},
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail(),
            "code": exc.code,
            "error": True,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # §63 : dernier rempart — jamais de stack trace brute au client ;
    # le 500 reste cohérent avec les autres réponses d'erreur.
    log_event(
        "UNHANDLED_ERROR",
        level="ERROR",
        message=f"Exception non gérée: {type(exc).__name__}: {exc}",
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Erreur interne — consultez les logs.",
            "code": "unhandled_error",
            "error": True,
        },
    )


@app.get("/")
def root():
    return {
        "name": "Agent Control Center API",
        "docs": "/docs",
        "health": "/api/health",
    }
