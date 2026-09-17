# Routes Models — GET /api/models (Mission Assistant UI)
#
# Liste les modèles Ollama disponibles + le modèle actif, pour le
# ModelSelector officiel d'assistant-ui. Lecture seule : ce module
# ne fait AUCUNE décision pédagogique — il expose uniquement ce
# que l'instance Ollama locale/cloud propose.
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import MODEL_NAME, OLLAMA_HOST, ollama_headers

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


def _list_ollama_models() -> list[dict[str, Any]]:
    """Tags Ollama — liste brute. Silencieux si indisponible."""
    try:
        import ollama

        client = ollama.Client(
            host=OLLAMA_HOST,
            headers=ollama_headers() or {},
        )
        response = client.list()
        models = []
        for entry in (response.models or []):
            raw = getattr(entry, "model", None) or ""
            if not raw:
                continue
            # taille lisible si dispo (ex: "4.7 GB")
            size = getattr(entry, "size", None)
            models.append(
                {"id": raw, "name": raw, "size": size}
            )
        return models
    except Exception:
        return []


@router.get("", response_model=ModelsResponse)
def api_list_models() -> ModelsResponse:
    """Modèles disponibles + modèle actif (ModelSelector assistant-ui)."""
    raw = _list_ollama_models()

    # Déduplication par id, tri stable alphabétique
    seen: dict[str, dict[str, Any]] = {}
    for m in raw:
        if m["id"] not in seen:
            seen[m["id"]] = m
    ids = sorted(seen.keys())

    models = [
        ModelInfo(
            id=i,
            name=i,
            description=_size_label(seen[i].get("size")),
            active=(i == MODEL_NAME),
        )
        for i in ids
    ]

    # Le modèle actif doit toujours être sélectionnable, même si
    # Ollama ne répond pas (sinon le ModelSelector serait vide).
    if MODEL_NAME not in seen:
        models.insert(
            0,
            ModelInfo(
                id=MODEL_NAME,
                name=MODEL_NAME,
                description="modèle actif",
                active=True,
            ),
        )

    return ModelsResponse(models=models, active_model=MODEL_NAME)


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
