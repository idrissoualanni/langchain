# Model Registry — Source de vérité des modèles (§6-§7)
#
# Le registry maintient la liste des modèles configurés avec leurs
# capacités. Il lit depuis models.yaml et permet à l'admin de gérer
# les configurations via API.
#
# Responsabilités :
#   - Charger les modèles depuis YAML/env
#   - Exposer les capacités
#   - Valider les configurations admin
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.services.models.schemas import ModelConfig
from app.schemas.model_capabilities import (
    ModelCapabilities,
    get_model_capabilities,
    list_configured_models,
)


# Ancré sur app/ (parents[2] depuis app/services/models/) — ne pas
# utiliser parents[1] (services/) : le YAML vit à la racine du package.
_MODELS_YAML = Path(__file__).resolve().parents[2] / "models.yaml"
_cache: dict | None = None


def _load_yaml(path: Path | None = None) -> dict:
    """Charge models.yaml — dict vide si absent."""
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


def get_model_config(model_id: str, path: Path | None = None) -> ModelConfig | None:
    """Récupère la config d'un modèle par son ID logique.
    
    Retourne None si le modèle n'existe pas dans le registry.
    """
    data = _load_yaml(path)
    models = data.get("models", {}) or {}
    
    if model_id not in models:
        return None
    
    entry = models[model_id]
    if not isinstance(entry, dict):
        return None
    
    # Construire ModelCapabilities depuis l'entrée YAML
    caps = ModelCapabilities(
        provider=entry.get("provider", "ollama"),
        model_name=entry.get("model", model_id),
        context_window=entry.get("context_window"),
        reserved_output_tokens=entry.get("reserved_output_tokens", 2048),
        max_output_tokens=entry.get("max_output_tokens"),
        supports_tools=entry.get("supports_tools", False),
        supports_structured_output=entry.get("supports_structured_output", False),
        supports_vision=entry.get("supports_vision", False),
        supports_audio=entry.get("supports_audio", False),
    )
    
    return ModelConfig(
        id=model_id,
        display_name=entry.get("display_name", model_id),
        provider=entry.get("provider", "ollama"),
        model_name=entry.get("model", model_id),
        gateway_model=entry.get("gateway_model"),
        enabled=entry.get("enabled", True),
        context_window=entry.get("context_window"),
        max_output_tokens=entry.get("max_output_tokens"),
        capabilities=caps,
        metadata=entry.get("metadata", {}),
    )


def list_all_model_configs(path: Path | None = None) -> list[ModelConfig]:
    """Liste tous les modèles configurés avec leurs configs complètes."""
    data = _load_yaml(path)
    models = data.get("models", {}) or {}
    
    configs = []
    for model_id, entry in models.items():
        if not isinstance(entry, dict):
            continue
        
        caps = ModelCapabilities(
            provider=entry.get("provider", "ollama"),
            model_name=entry.get("model", model_id),
            context_window=entry.get("context_window"),
            reserved_output_tokens=entry.get("reserved_output_tokens", 2048),
            max_output_tokens=entry.get("max_output_tokens"),
            supports_tools=entry.get("supports_tools", False),
            supports_structured_output=entry.get("supports_structured_output", False),
            supports_vision=entry.get("supports_vision", False),
            supports_audio=entry.get("supports_audio", False),
        )
        
        configs.append(ModelConfig(
            id=model_id,
            display_name=entry.get("display_name", model_id),
            provider=entry.get("provider", "ollama"),
            model_name=entry.get("model", model_id),
            gateway_model=entry.get("gateway_model"),
            enabled=entry.get("enabled", True),
            context_window=entry.get("context_window"),
            max_output_tokens=entry.get("max_output_tokens"),
            capabilities=caps,
            metadata=entry.get("metadata", {}),
        ))
    
    return configs


def save_model_config(config: ModelConfig, path: Path | None = None) -> bool:
    """Sauvegarde/mise à jour d'un modèle dans le registry.
    
    Retourne True si succès, False si échec.
    """
    target_path = path or _MODELS_YAML
    
    try:
        data = _load_yaml(target_path)
        if "models" not in data:
            data["models"] = {}
        
        # Convertir ModelConfig en dict YAML
        entry = {
            "provider": config.provider,
            "model": config.model_name,
            "display_name": config.display_name or config.id,
            "enabled": config.enabled,
        }
        
        if config.gateway_model:
            entry["gateway_model"] = config.gateway_model
        if config.context_window is not None:
            entry["context_window"] = config.context_window
        if config.max_output_tokens is not None:
            entry["max_output_tokens"] = config.max_output_tokens
        if config.capabilities.provider != "ollama":
            entry["provider"] = config.capabilities.provider
        entry["supports_tools"] = config.capabilities.supports_tools
        entry["supports_structured_output"] = config.capabilities.supports_structured_output
        entry["supports_vision"] = config.capabilities.supports_vision
        entry["supports_audio"] = config.capabilities.supports_audio
        
        data["models"][config.id] = entry
        
        with open(target_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        
        # Invalider le cache
        global _cache
        _cache = None
        
        return True
    except Exception:
        return False


def delete_model_config(model_id: str, path: Path | None = None) -> bool:
    """Supprime un modèle du registry.
    
    Retourne True si succès, False si échec ou modèle inexistant.
    """
    target_path = path or _MODELS_YAML
    
    try:
        data = _load_yaml(target_path)
        models = data.get("models", {}) or {}
        
        if model_id not in models:
            return False
        
        del data["models"][model_id]
        
        with open(target_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        
        # Invalider le cache
        global _cache
        _cache = None
        
        return True
    except Exception:
        return False


def get_default_model_id(path: Path | None = None) -> str:
    """Retourne l'ID du modèle par défaut (vrai défaut, jamais inventé).

    Règles déterministes :
      1. la clé YAML `default` (si elle existe ET est enabled)
      2. sinon le premier modèle enabled du registry
      3. sinon "" (aucun défaut — l'appelant décide de l'erreur)
    """
    data = _load_yaml(path)
    models = data.get("models", {}) or {}

    default_entry = models.get("default")
    if isinstance(default_entry, dict) and default_entry.get("enabled", True):
        return "default"

    for model_id, entry in models.items():
        if isinstance(entry, dict) and entry.get("enabled", True):
            return model_id

    return ""


def find_model_config(
    identifier: str,
    path: Path | None = None,
) -> ModelConfig | None:
    """Cherche un modèle par id logique OU par nom réel (model_name).

    Restriction ModelSelector (§mission) : un choix client est accepté
    uniquement s'il correspond à un modèle ENREGISTRÉ (id ou model_name
    du registry). L'appelant vérifie ensuite `enabled`.
    """
    if not identifier:
        return None
    config = get_model_config(identifier, path=path)
    if config is not None:
        return config
    identifier_l = identifier.strip().lower()
    for candidate in list_all_model_configs(path=path):
        if candidate.model_name.strip().lower() == identifier_l:
            return candidate
    return None


__all__ = [
    "get_model_config",
    "find_model_config",
    "list_all_model_configs",
    "save_model_config",
    "delete_model_config",
    "get_default_model_id",
    "_load_yaml",
]
