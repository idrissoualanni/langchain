# Routes Models — GET /api/models (Mission Assistant UI)
#
# Liste les modèles Ollama disponibles + le modèle actif, pour le
# ModelSelector officiel d'assistant-ui. Lecture seule : ce module
# ne fait AUCUNE décision pédagogique — il expose uniquement ce
# que l'instance Ollama locale/cloud propose.
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import OLLAMA_HOST, ollama_headers
from app.schemas.model_capabilities import list_configured_models
from app.services.models.registry import get_default_model_id

router = APIRouter(prefix="/api/models", tags=["models"])


class ModelInfo(BaseModel):
    """Un modèle disponible (miroir du ModelSelector assistant-ui)."""
    id: str
    name: str
    description: str = ""
    active: bool = False


class ModelsResponse(BaseModel):
    models: list[ModelInfo]
    active_model: str


@router.get("", response_model=ModelsResponse)
def api_list_models() -> ModelsResponse:
    """Modèles disponibles + modèle actif (ModelSelector assistant-ui).

    Source : `models.yaml` (Model Capability Registry, §38) — la
    liste reflète STRICTEMENT les modèles CONFIGURÉS et activés.
    """
    configured = list_configured_models()
    active_id = get_default_model_id()

    models = [
        ModelInfo(
            id=c["id"],
            name=c["id"],
            description=f"{c['provider']} · configuré",
            active=(c["id"] == active_id),
        )
        for c in configured
        if c.get("enabled", True)
    ]

    # Trier par activité (actif en premier), puis par id
    models.sort(key=lambda m: (not m.active, m.id))

    return ModelsResponse(models=models, active_model=active_id)


def _size_label(size: Any) -> str:
    """Taille lisible ou chaîne vide."""
    try:
        if size is None:
            return ""
        gb = float(size) / 1_000_000_000
        if gb >= 1:
            return f"{gb:.1f} GB"
        mb = float(size) / 1_000_000
        return f"{mb:.0f} MB"
    except Exception:
        return ""
