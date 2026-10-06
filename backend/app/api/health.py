# Route Health — GET /api/health
import base64
import os

import requests
from fastapi import APIRouter, Response

from app.schemas import HealthResponse
from app.config import (
    check_ollama_health,
    check_database_health,
    langsmith_settings,
    langfuse_settings,
    cloudflare_ai_settings,
    CF_AI_DEFAULT_MODEL,
)
from app.auth.resolver import auth_mode, jwks_reachable
from app.infrastructure.observability.langsmith_client import get_langsmith_client
from app.services.models.registry import get_default_model_id, get_model_config


def langfuse_sdk_available() -> bool:
    """Le package `langfuse` est-il importable ?

    Séparé de ``is_enabled()`` (config) parce que les deux échouent
    différemment : une config activée sans package installé donne un
    no-op SILENCIEUX — l'app trace rien sans jamais lever.
    """
    try:
        import importlib.util

        return importlib.util.find_spec("langfuse") is not None
    except Exception:
        return False


router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("", response_model=HealthResponse)
def api_health() -> HealthResponse:
    """Statut des composants : Ollama, LangGraph, base Neon."""
    # Vérification légère sans importer le graph complet
    langgraph_ok = True  # On suppose OK si l'app démarre

    # Modèle défaut : registry models.yaml (source de vérité §6-§7) —
    # l'ancienne variable d'env MODEL_NAME a été supprimée.
    default_id = get_default_model_id()
    default_cfg = get_model_config(default_id) if default_id else None

    return HealthResponse(
        status="ok" if langgraph_ok else "degraded",
        ollama=check_ollama_health(),
        langgraph=langgraph_ok,
        database=check_database_health(),
        model=default_cfg.model_name if default_cfg else "",
    )


@router.get("/ready")
def health_ready(response: Response) -> dict:
    """Vérifie que le service est prêt à accepter des requêtes.

    §62 : un readiness qui répond 200 même non-prêt est un anti-pattern
    (le scheduler/orchestrateur ne détecte jamais l'indisponibilité) →
    HTTP 503 tant qu'un composant critique (Ollama/base Neon) est KO.
    """
    ollama_ok = check_ollama_health()
    database_ok = check_database_health()
    
    # Vérification légère sans importer le graph complet
    agent_ok = True
    
    ready = ollama_ok and database_ok and agent_ok
    if not ready:
        response.status_code = 503
    
    return {
        "ready": ready,
        "checks": {
            "ollama": ollama_ok,
            "database": database_ok,
            "agent": agent_ok,
        },
    }


@router.get("/model-gateway")
def health_model_gateway() -> dict:
    """Vérifie le Model Gateway (LiteLLM ou fallback)."""
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


@router.get("/langfuse")
def health_langfuse() -> dict:
    """Vérifie la connectivité Langfuse Cloud (us.cloud.langfuse.com).

    Deux contrôles distincts, volontairement non fusionnés :

    - ``server_ok`` : ``GET /api/public/health`` — le serveur répond-il ?
      Ne demande PAS de clé, donc reste vert même avec des clés fausses.
    - ``keys_ok`` : ``GET /api/public/projects`` avec Basic auth — les
      clés sont-elles valides etgives-elles accès à un projet ?

    ``connected`` n'est vrai que si les DEUX passent : un serveur qui
    répond avec des clés invalides n'est pas une intégration fonctionnelle.

    Ces deux endpoints sont ceux qui existent en Langfuse v4. Le chemin
    ``/api/public/auth-check``, borrowé d'exemples plus anciens, renvoie
    404 sur v4 — s'en servir donnait un faux négatif de configuration.
    """
    settings = langfuse_settings()
    configured = bool(
        settings.public_key and settings.secret_key and settings.base_url
    )

    result: dict = {
        # settings.enabled = LANGFUSE_ENABLED ; sdk_available = le package
        # `langfuse` est importable. Les deux sont nécessaires : activer
        # l'env sans installer le SDK laisse un no-op silencieux.
        "enabled": settings.enabled,
        "sdk_available": langfuse_sdk_available(),
        "configured": configured,
        "base_url": settings.base_url,
        "target_cloud": "us.cloud.langfuse.com" in (settings.base_url or ""),
        "server_ok": False,
        "keys_ok": False,
        "connected": False,
    }

    if not configured:
        return result

    basic = base64.b64encode(
        f"{settings.public_key}:{settings.secret_key}".encode()
    ).decode()
    headers = {"Authorization": f"Basic {basic}"}

    try:
        resp = requests.get(
            f"{settings.base_url.rstrip('/')}/api/public/health", timeout=10
        )
        result["server_ok"] = resp.status_code == 200
        if resp.status_code == 200:
            # La version serveur aide à diagnostiquer un écart SDK/serveur.
            try:
                result["server_version"] = resp.json().get("version")
            except Exception:
                pass
    except Exception as e:
        result["error"] = f"health: {e}"

    try:
        resp = requests.get(
            f"{settings.base_url.rstrip('/')}/api/public/projects",
            headers=headers,
            timeout=10,
        )
        result["keys_ok"] = resp.status_code == 200
        if resp.status_code == 200:
            try:
                projects = resp.json().get("data") or []
                result["projects"] = [
                    p.get("name") for p in projects[:5] if isinstance(p, dict)
                ]
            except Exception:
                pass
        elif resp.status_code in (401, 403):
            result["error"] = f"Clés refusées ({resp.status_code})"
        else:
            result["error"] = f"projects: HTTP {resp.status_code}"
    except Exception as e:
        result["error"] = result.get("error") or f"projects: {e}"

    result["connected"] = bool(result["server_ok"] and result["keys_ok"])
    return result


@router.get("/auth")
def health_auth() -> dict:
    """État de l'authentification : mode et joignabilité du JWKS.

    Neon Managed Auth est le seul fournisseur d'identité : c'est son
    well-known qui est testé ( voir jwks_reachable ). Le JWKS étant
    publique, aucune donnée sensible n'est renvoyée.
    """
    return {
        "mode": auth_mode(),
        "jwks_reachable": jwks_reachable(),
    }


@router.get("/cloudflare")
def health_cloudflare() -> dict:
    """Vérifie la connectivité Cloudflare Workers AI.

    Interroge l'endpoint NATIF (``{api_root}/run/{model}``) plutôt que la
    base OpenAI-compatible : c'est le même chemin que celui utilisé par
    les embeddings, donc le test valide réellement le compte Cloudflare
    (droits AI + token) et pas seulement la forme d'URL.

    Ne renvoie JAMAIS le token — seulement un préfixe de 4 caractères,
    suffisant pour distinguer deux credentials sans les exposer.
    """
    settings = cloudflare_ai_settings()
    result: dict = {
        "enabled": settings.enabled,
        "configured": bool(settings.account_id and settings.api_token),
        "account_id": settings.account_id[:8] + "..." if settings.account_id else None,
        "api_root": settings.api_root,
        "openai_base_url": settings.base_url,
        "token_prefix": settings.api_token[:4] if settings.api_token else None,
        "connected": False,
    }

    if settings.enabled and settings.account_id and settings.api_token:
        url = f"{settings.api_root}/run/{CF_AI_DEFAULT_MODEL}"
        try:
            resp = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.api_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
                timeout=30,
            )
            result["connected"] = resp.status_code == 200
            result["status_code"] = resp.status_code
            if resp.status_code != 200:
                # 400/401/403 = problème de droits/token ; 429 = quota.
                result["error"] = resp.text[:200]
        except Exception as e:
            result["error"] = str(e)

    return result
