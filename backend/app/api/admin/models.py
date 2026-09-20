# Routes Admin Models — CRUD pour Model Registry (§28)
#
# GET    /api/admin/models          → liste tous les modèles
# POST   /api/admin/models          → crée un modèle
# PATCH  /api/admin/models/{id}     → met à jour un modèle
# DELETE /api/admin/models/{id}     → supprime un modèle
# POST   /api/admin/models/{id}/test → teste une configuration
#
# Sécurité : réservé aux admins (vérification ADMIN_CLERK_IDS)
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.resolver import CurrentUser, require_admin
from app.models.registry import (
    get_model_config,
    list_all_model_configs,
    save_model_config,
    delete_model_config,
    get_default_model_id,
)
from app.models.schemas import ModelConfig, ModelCapabilities
from app.models.gateway import create_llm_from_config


router = APIRouter(prefix="/api/admin/models", tags=["admin-models"])


class ModelCreate(BaseModel):
    """Schéma de création d'un modèle."""
    
    id: str
    display_name: str = ""
    provider: str = "ollama"
    model_name: str = ""
    gateway_model: str | None = None
    enabled: bool = True
    context_window: int | None = None
    max_output_tokens: int | None = None
    supports_tools: bool = False
    supports_structured_output: bool = False
    supports_vision: bool = False
    supports_audio: bool = False
    metadata: dict = Field(default_factory=dict)


class ModelUpdate(BaseModel):
    """Schéma de mise à jour partielle d'un modèle."""
    
    display_name: str | None = None
    provider: str | None = None
    model_name: str | None = None
    gateway_model: str | None = None
    enabled: bool | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    supports_tools: bool | None = None
    supports_structured_output: bool | None = None
    supports_vision: bool | None = None
    supports_audio: bool | None = None
    metadata: dict | None = None


class ModelTestRequest(BaseModel):
    """Requête de test d'un modèle."""
    
    prompt: str = "Hello"
    temperature: float = 0.0
    max_tokens: int | None = None


class ModelTestResponse(BaseModel):
    """Réponse de test d'un modèle."""
    
    success: bool
    model_id: str
    response: str = ""
    error: str = ""


class ModelListResponse(BaseModel):
    """Réponse liste des modèles."""
    
    models: list[ModelConfig]
    default_model: str


@router.get("", response_model=ModelListResponse)
def admin_list_models(
    current_user: CurrentUser = Depends(require_admin),
) -> ModelListResponse:
    """Liste tous les modèles configurés (admin only)."""
    models = list_all_model_configs()
    default = get_default_model_id()
    return ModelListResponse(models=models, default_model=default)


@router.post("", response_model=ModelConfig, status_code=status.HTTP_201_CREATED)
def admin_create_model(
    data: ModelCreate,
    current_user: CurrentUser = Depends(require_admin),
) -> ModelConfig:
    """Crée un nouveau modèle (admin only)."""
    # Vérifier si déjà existe
    existing = get_model_config(data.id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Model {data.id} already exists",
        )
    
    config = ModelConfig(
        id=data.id,
        display_name=data.display_name or data.id,
        provider=data.provider,
        model_name=data.model_name or data.id,
        gateway_model=data.gateway_model,
        enabled=data.enabled,
        context_window=data.context_window,
        max_output_tokens=data.max_output_tokens,
        capabilities=ModelCapabilities(
            provider=data.provider,
            model_name=data.model_name or data.id,
            supports_tools=data.supports_tools,
            supports_structured_output=data.supports_structured_output,
            supports_vision=data.supports_vision,
            supports_audio=data.supports_audio,
        ),
        metadata=data.metadata,
    )
    
    if not save_model_config(config):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save model configuration",
        )
    
    return config


@router.patch("/{model_id}", response_model=ModelConfig)
def admin_update_model(
    model_id: str,
    data: ModelUpdate,
    current_user: CurrentUser = Depends(require_admin),
) -> ModelConfig:
    """Met à jour un modèle existant (admin only)."""
    config = get_model_config(model_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {model_id} not found",
        )
    
    # Appliquer les champs mis à jour
    update_data = data.model_dump(exclude_unset=True)
    updated_config = config.model_copy(update=update_data)
    
    # Mettre à jour capabilities si nécessaire
    cap_updates = {}
    for field in ["supports_tools", "supports_structured_output", 
                  "supports_vision", "supports_audio", "provider", "model_name"]:
        if getattr(data, field, None) is not None:
            cap_updates[field] = getattr(data, field)
    
    if cap_updates:
        updated_caps = config.capabilities.model_copy(update=cap_updates)
        updated_config = updated_config.model_copy(
            update={"capabilities": updated_caps}
        )
    
    if not save_model_config(updated_config):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update model configuration",
        )
    
    return updated_config


@router.delete("/{model_id}")
def admin_delete_model(
    model_id: str,
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """Supprime un modèle (admin only)."""
    if not delete_model_config(model_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {model_id} not found or cannot be deleted",
        )
    
    return {"success": True, "deleted": model_id}


@router.post("/{model_id}/test", response_model=ModelTestResponse)
def admin_test_model(
    model_id: str,
    data: ModelTestRequest,
    current_user: CurrentUser = Depends(require_admin),
) -> ModelTestResponse:
    """Teste une configuration de modèle (admin only).
    
    Ne renvoie JAMAIS les secrets (API keys, etc.).
    """
    try:
        llm = create_llm_from_config(
            model_id=model_id,
            temperature=data.temperature,
            max_tokens=data.max_tokens,
        )
        
        # Appel simple pour tester
        response = llm.invoke(data.prompt)
        
        return ModelTestResponse(
            success=True,
            model_id=model_id,
            response=str(response.content)[:500],  # Tronqué pour sécurité
        )
    except Exception as e:
        return ModelTestResponse(
            success=False,
            model_id=model_id,
            error=str(e)[:200],  # Message d'erreur tronqué
        )


@router.get("/{model_id}", response_model=ModelConfig)
def admin_get_model(
    model_id: str,
    current_user: CurrentUser = Depends(require_admin),
) -> ModelConfig:
    """Récupère les détails d'un modèle (admin only)."""
    config = get_model_config(model_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {model_id} not found",
        )
    return config


__all__ = ["router"]
