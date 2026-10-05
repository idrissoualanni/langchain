from fastapi import APIRouter, HTTPException, Depends
from typing import Any
from pydantic import BaseModel
import httpx

from app.api.deps import get_current_admin
from app.services.models.provider_registry import (
    list_providers,
    get_provider_config,
    save_provider_config,
    ProviderConfig,
    resolve_base_url,
    resolve_auth_headers,
)
from app.services.models.client_factory import invalidate_client_cache

router = APIRouter(prefix="/providers", tags=["Admin Providers"])

class ProviderUpdate(BaseModel):
    display_name: str | None = None
    enabled: bool | None = None
    base_url: str | None = None
    base_url_env: str | None = None
    base_url_default: str | None = None
    api_path: str | None = None
    # Auth updates
    api_key: str | None = None
    api_key_env: str | None = None
    auth_type: str | None = None # mapped to auth.type
    # Extra headers
    extra_headers: dict[str, str] | None = None

@router.get("")
async def get_providers(admin=Depends(get_current_admin)):
    """Liste tous les providers configurés."""
    return list_providers(enabled_only=False)


@router.get("/{provider_id}/available-models", response_model=list[str])
async def get_available_models(provider_id: str, admin=Depends(get_current_admin)):
    """Liste les modèles disponibles auprès du provider en interrogeant son API."""
    provider = get_provider_config(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' introuvable")

    # On ne supporte l'auto-découverte que pour les providers compatibles OpenAI ou Ollama
    if provider.type not in ["openai_compatible", "ollama"]:
        raise HTTPException(
            status_code=400,
            detail=f"Auto-découverte non supportée pour le type de provider '{provider.type}'"
        )

    try:
        base_url = resolve_base_url(provider)
        headers = resolve_auth_headers(provider)

        # Construction de l'URL /models
        # Pour Ollama, c'est /api/tags
        endpoint = "/api/tags" if provider.type == "ollama" else "/v1/models"
        url = base_url.rstrip("/") + endpoint

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

            if provider.type == "ollama":
                # Format Ollama: {"models": [{"name": "...", ...}, ...]}
                return [m["name"] for m in data.get("models", [])]
            else:
                # Format OpenAI: {"data": [{"id": "...", ...}, ...]}
                return [m["id"] for m in data.get("data", [])]

    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Erreur API provider: {e.response.text}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"Échec de la connexion au provider: {str(e)}"
        )


@router.patch("/{provider_id}")
async def update_provider(provider_id: str, update: ProviderUpdate, admin=Depends(get_current_admin)):
    """Met à jour la configuration d'un provider."""
    provider = get_provider_config(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' introuvable")

    # On travaille sur un dump pour la persistance
    config_data = provider.model_dump()

    # Mise à jour des champs de base
    if update.display_name is not None:
        config_data["display_name"] = update.display_name
    if update.enabled is not None:
        config_data["enabled"] = update.enabled
    if update.base_url is not None:
        config_data["base_url"] = update.base_url
    if update.base_url_env is not None:
        config_data["base_url_env"] = update.base_url_env
    if update.base_url_default is not None:
        config_data["base_url_default"] = update.base_url_default
    if update.api_path is not None:
        config_data["api_path"] = update.api_path

    # Mise à jour de l'auth
    auth_data = config_data["auth"]
    if update.auth_type is not None:
        auth_data["type"] = update.auth_type
    if update.api_key is not None:
        auth_data["api_key"] = update.api_key
    if update.api_key_env is not None:
        auth_data["api_key_env"] = update.api_key_env
    config_data["auth"] = auth_data

    # Mise à jour des headers
    if update.extra_headers is not None:
        config_data["extra_headers"] = update.extra_headers

    # Persistance
    save_provider_config(provider_id, config_data)

    # Invalidation du cache des clients LLM pour appliquer les changements immédiatement
    invalidate_client_cache()

    return {"status": "success", "provider_id": provider_id}
