# FastAPI — Agent Control Center backend
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.graph import get_agent
from app.api import chat, health, logs, memory, subjects, threads, users
from app.db.connections import init_db
from app.logging.events import log_event, setup_logging
from app.logging.sse import sse_events
from app.ws.logs import router as ws_router


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

# CORS — frontend dev Vite
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes API
app.include_router(users.router)
app.include_router(threads.router)
app.include_router(chat.router)
app.include_router(memory.router)
app.include_router(logs.router)
app.include_router(health.router)
app.include_router(subjects.router)

# SSE — événements agent temps réel
app.add_api_route(
    "/api/events",
    sse_events,
    methods=["GET"],
)

# WebSocket — alternative logs temps réel
app.include_router(ws_router)


@app.get("/")
def root():
    return {
        "name": "Agent Control Center API",
        "docs": "/docs",
        "health": "/api/health",
    }
