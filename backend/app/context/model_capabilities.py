# Model Capability Registry V6.8 (§37-§39, §49-§51).
#
# Abstraction centralisée des capacités des modèles, chargée
# depuis app/models.yaml (source déclarative unique).
#
# §38 — pas de duplication de config :
#   - le NOM du modèle actif vient de l'env (MODEL_OLLAMA, app/config.py)
#   - les CAPACITÉS viennent de models.yaml
#   - SubjectConfig.model reste compatible : si une matière déclare
#     un modèle, ses capacités sont lookup ici
# Jamais trois sources contradictoires : le YAML ne décrit QUE
# des capacités, l'env QUE le choix actif.
#
# §37/§39 : les capacités inconnues sont null/false — RIEN n'est
# inventé (un modèle non déclaré hérite des capacités default,
# sans_gain : pas de capability fabriquée).
import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

_MODELS_YAML = Path(__file__).resolve().parents[1] / "models.yaml"

# Cache du YAML chargé (invalidé par _load(force=True) en tests)
_cache: dict | None = None


class ModelCapabilities(BaseModel):
    """Capacités d'un modèle (§39) — champs null si inconnu."""

    provider: str = "ollama"
    model_name: str = "default"
    context_window: int | None = Field(
        default=None,
        description="Fenêtre de contexte en tokens — null = "
        "inconnue → fallback conservateur (budget.py)",
    )
    reserved_output_tokens: int = Field(
        default=2048,
        description="Tokens réservés pour la sortie (§40)",
    )
    max_output_tokens: int | None = None
    supports_tools: bool = False
    supports_structured_output: bool = False
    supports_vision: bool = False
    supports_audio: bool = False


def _load(path: Path | None = None) -> dict:
    """Charge models.yaml — dict vide si absent (defaults)."""
    global _cache
    if path is None and _cache is not None:
        return _cache
    try:
        with open(path or _MODELS_YAML, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        data = {}
    if path is None:
        _cache = data
    return data


def _entry_to_caps(entry: dict, model_name: str) -> ModelCapabilities:
    """Convertit une entrée YAML en ModelCapabilities."""
    return ModelCapabilities(
        provider=entry.get("provider", "ollama"),
        model_name=model_name,
        context_window=entry.get("context_window"),
        reserved_output_tokens=entry.get(
            "reserved_output_tokens", 2048
        ),
        max_output_tokens=entry.get("max_output_tokens"),
        supports_tools=entry.get("supports_tools", False),
        supports_structured_output=entry.get(
            "supports_structured_output", False
        ),
        supports_vision=entry.get("supports_vision", False),
        supports_audio=entry.get("supports_audio", False),
    )


def get_model_capabilities(
    model_name: str | None = None,
    path: Path | None = None,
) -> ModelCapabilities:
    """Capacités d'un modèle (§37).

    - model_name None → modèle ACTIF (env MODEL_OLLAMA) ;
      si l'env ne nomme pas une entrée du YAML → entrée default
    - nom = clé du YAML → cette entrée
    - nom inconnu → capacités default clonées avec model_name
      remplacé (JAMAIS de capacité inventée, §19/§37)
    """
    data = _load(path)
    models = data.get("models", {}) or {}
    default_entry = models.get("default", {}) or {}

    if model_name is None:
        model_name = os.getenv("MODEL_OLLAMA", "") or (
            default_entry.get("model", "default")
        )

    if model_name in models and model_name != "default":
        return _entry_to_caps(models[model_name], model_name)

    # default, ou inconnu → capacités default (honnêtes)
    return _entry_to_caps(default_entry, model_name)


def list_configured_models(
    path: Path | None = None,
) -> list[dict]:
    """Modèles RÉELLEMENT configurés dans models.yaml (§38).

    Chaque entrée `models.<clé>` décrit un modèle : on expose son
    nom réel (`.model`, la valeur envoyée à Ollama) — jamais la clé
    logique ("default" n'est PAS un modèle Ollama). Dédoublonnage
    par nom réel ; tri stable par nom. YAML absent/vide → liste vide
    (l'appelant décide du repli). Conserve le principe "une seule
    source" : on lit le même _load() que get_model_capabilities.
    """
    data = _load(path)
    raw = data.get("models", {}) or {}
    seen: dict[str, str] = {}
    provider_by_id: dict[str, str] = {}
    for key, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        model = (entry.get("model") or key or "").strip()
        if not model:
            continue
        if model not in seen:
            seen[model] = key
            provider_by_id[model] = entry.get("provider", "ollama")
    entries = [
        {
            "id": mid,
            "key": seen[mid],
            "provider": provider_by_id.get(mid, "ollama"),
        }
        for mid in sorted(seen.keys())
    ]
    return entries


def supports(
    caps: ModelCapabilities,
    capability: Literal[
        "tools", "structured_output", "vision", "audio"
    ],
) -> bool:
    """§49 : le modèle supporte-t-il cette capacité ?

    Avant une action nécessitant une capacité (structured output,
    vision, audio, tool calling) : False → graceful fallback
    (§49) — jamais de crash, jamais d'invention.
    """
    mapping = {
        "tools": caps.supports_tools,
        "structured_output": caps.supports_structured_output,
        "vision": caps.supports_vision,
        "audio": caps.supports_audio,
    }
    return bool(mapping.get(capability, False))


__all__ = [
    "ModelCapabilities",
    "get_model_capabilities",
    "list_configured_models",
    "supports",
]
