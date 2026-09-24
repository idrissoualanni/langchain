# FastAPI — Agent Control Center backend
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.graph.main import get_agent
from app.api import (
    activity,
    chat,
    context,
    documents,
    health,
    learning,
    livekit,
    logs,
    memory,
    models,
    subjects,
    threads,
    users,
)
from app.api.admin import (
    models_router as admin_models_router,
    knowledge_router as admin_knowledge_router,
    observability_router as admin_observability_router,
    dashboard_router as admin_dashboard_router,
)
from app.infrastructure.database.connections import init_db
from app.logging.events import log_event, setup_logging
from app.logging.sse import sse_events
from app.ws.logs import router as ws_router
from app.config import ALLOWED_ORIGINS


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup : logging + DB + agent warm-up + loop registration."""
    setup_logging()
    init_db()

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
            message="LangGraph agent initialized with SqliteSaver",
        )
    except Exception as exc:
        log_event(
            "AGENT_INIT_ERROR",
            level="ERROR",
            message=f"Agent init failed: {exc}",
        )

    yield

    log_event("SERVER_STOP", message="Backend shutting down")


app = FastAPI(
    title="Agent Control Center API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — frontend (dev Vite local + domaines Vercel via env)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
app.include_router(livekit.router)

# Admin API — Model/Knowledge/Observability/Dashboard management (secured)
# Les routers models/knowledge portent déjà leur préfixe /api/admin/...
# complet ; observability/dashboard utilisent /observability et /dashboard.
app.include_router(admin_models_router, tags=["admin-models"])
app.include_router(admin_knowledge_router, tags=["admin-knowledge"])
app.include_router(admin_observability_router, prefix="/api/admin", tags=["admin-observability"])
app.include_router(admin_dashboard_router, prefix="/api/admin", tags=["admin-dashboard"])

# SSE — événements agent temps réel
app.add_api_route(
    "/api/events",
    sse_events,
    methods=["GET"],
)

# WebSocket — alternative logs temps réel
app.include_router(ws_router)


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
