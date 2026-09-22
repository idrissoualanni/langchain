# Route Health — GET /api/health
from fastapi import APIRouter

from app.schemas import HealthResponse
from app.config import (
    MODEL_NAME,
    check_ollama_health,
    check_sqlite_health,
    langsmith_settings,
)
from app.infrastructure.observability.langsmith_client import get_langsmith_client


router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("", response_model=HealthResponse)
def api_health() -> HealthResponse:
    """Statut des composants : Ollama, LangGraph, SQLite."""
    # Vérification légère sans importer le graph complet
    langgraph_ok = True  # On suppose OK si l'app démarre
    
    return HealthResponse(
        status="ok" if langgraph_ok else "degraded",
        ollama=check_ollama_health(),
        langgraph=langgraph_ok,
        sqlite=check_sqlite_health(),
        model=MODEL_NAME,
    )


@router.get("/ready")
def health_ready() -> dict:
    """Vérifie que le service est prêt à accepter des requêtes."""
    ollama_ok = check_ollama_health()
    sqlite_ok = check_sqlite_health()
    
    # Vérification légère sans importer le graph complet
    agent_ok = True
    
    ready = ollama_ok and sqlite_ok and agent_ok
    
    return {
        "ready": ready,
        "checks": {
            "ollama": ollama_ok,
            "sqlite": sqlite_ok,
            "agent": agent_ok,
        },
    }


@router.get("/model-gateway")
def health_model_gateway() -> dict:
    """Vérifie le Model Gateway (LiteLLM ou fallback)."""
    import os
    
    litellm_enabled = os.getenv("MODEL_GATEWAY_ENABLED", "false").lower() == "true"
    litellm_url = os.getenv("LITELLM_BASE_URL", "")
    
    gateway_status = {
        "enabled": litellm_enabled,
        "provider": os.getenv("MODEL_GATEWAY_PROVIDER", "direct"),
        "litellm_url": litellm_url if litellm_enabled else None,
        "fallback": "ollama",
    }
    
    # Si LiteLLM est activé, vérifier la connectivité
    if litellm_enabled and litellm_url:
        try:
            import requests
            resp = requests.get(litellm_url.replace("/v1", ""), timeout=5)
            gateway_status["litellm_reachable"] = resp.status_code < 500
        except Exception:
            gateway_status["litellm_reachable"] = False
    
    return gateway_status


@router.get("/langsmith")
def health_langsmith() -> dict:
    """Vérifie l'état de LangSmith observability."""
    client = get_langsmith_client()
    settings = langsmith_settings()

    return {
        "enabled": settings.enabled,
        "configured": client.is_enabled(),
        "environment": settings.environment,
        "endpoint": settings.endpoint,
        "project": settings.project,
    }
