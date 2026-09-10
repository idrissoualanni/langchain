# Route Health — GET /api/health
from fastapi import APIRouter

from app.agent.graph import get_agent
from app.api.schemas import HealthResponse
from app.config import (
    MODEL_NAME,
    check_ollama_health,
    check_sqlite_health,
)

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("", response_model=HealthResponse)
def api_health() -> HealthResponse:
    """Statut des composants : Ollama, LangGraph, SQLite."""
    try:
        get_agent()
        langgraph_ok = True
    except Exception:
        langgraph_ok = False

    return HealthResponse(
        status="ok" if langgraph_ok else "degraded",
        ollama=check_ollama_health(),
        langgraph=langgraph_ok,
        sqlite=check_sqlite_health(),
        model=MODEL_NAME,
    )
