# Provider Registry — Providers LLM configurables (pas hardcodés)
#
# Lit providers.yaml, expose les configs, et fabrique les clients.
# Nouveaux providers = éditer providers.yaml uniquement.

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from app.schemas.model_capabilities import ModelCapabilities


# ──────────────────────────────────────────────────────────────
# Schémas de configuration Provider
# ──────────────────────────────────────────────────────────────

class ProviderAuth(BaseModel):
    """Configuration d'authentification."""
    type: str = "bearer"  # bearer, x-api-key, custom, none
    api_key_env: str | None = None
    api_key: str | None = None
    required: bool = True


class ProviderConfig(BaseModel):
    """Configuration complète d'un provider LLM."""
    id: str
    type: str  # openai_compatible, ollama, anthropic, custom
    display_name: str = ""
    enabled: bool = True

    # URL de base
    base_url_env: str | None = None
    base_url_default: str | None = None
    base_url: str | None = None
    base_url_template: str | None = None  # Avec variables {VAR_NAME}
    base_url_vars: dict[str, str] = Field(default_factory=dict)  # var_name -> env_var
    api_path: str = ""
    
    # Auth
    auth: ProviderAuth = Field(default_factory=ProviderAuth)
    extra_headers: dict[str, str] = Field(default_factory=dict)
    extra_headers_env: str | None = None
    
    # Modèles et capacités
    supported_models: list[str] = Field(default_factory=list)
    default_capabilities: ModelCapabilities = Field(default_factory=ModelCapabilities)
    
    # Client custom
    client_class: str | None = None
    client_config: dict[str, Any] = Field(default_factory=dict)
    
    # Réseau
    timeout_seconds: int = 60
    max_retries: int = 2
    
    # Metadata
    metadata: dict[str, Any] = Field(default_factory=dict)


# ──────────────────────────────────────────────────────────────
# Registre des providers
# ──────────────────────────────────────────────────────────────

_PROVIDERS_YAML = Path(__file__).resolve().parents[2] / "providers.yaml"
_providers_cache: dict[str, ProviderConfig] | None = None


def _load_providers_yaml() -> dict:
    """Charge providers.yaml."""
    global _providers_cache
    if _providers_cache is not None:
        return {k: v.model_dump() for k, v in _providers_cache.items()}

    try:
        with open(_PROVIDERS_YAML, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        data = {}

    providers_data = data.get("providers", {}) or {}
    providers: dict[str, ProviderConfig] = {}

    for provider_id, entry in providers_data.items():
        if not isinstance(entry, dict):
            continue

        # Construire la config avec l'ID
        entry["id"] = provider_id

        # Résoudre default_capabilities si dict
        if "default_capabilities" in entry and isinstance(entry["default_capabilities"], dict):
            entry["default_capabilities"] = ModelCapabilities(**entry["default_capabilities"])

        # Résoudre auth si dict
        if "auth" in entry and isinstance(entry["auth"], dict):
            entry["auth"] = ProviderAuth(**entry["auth"])

        try:
            providers[provider_id] = ProviderConfig(**entry)
        except Exception as e:
            # Log mais continue pour ne pas casser les autres providers
            import logging
            logging.getLogger(__name__).warning(
                f"Provider '{provider_id}' invalide: {e}", exc_info=True
            )

    _providers_cache = providers
    return {k: v.model_dump() for k, v in providers.items()}


def save_provider_config(provider_id: str, config_data: dict) -> None:
    """Persiste la configuration d'un provider dans providers.yaml."""
    global _providers_cache

    # 1. Charger les données actuelles du fichier pour ne pas écraser les autres providers
    try:
        with open(_PROVIDERS_YAML, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        data = {}

    providers_data = data.get("providers", {}) or {}

    # 2. Mettre à jour ou créer le provider
    # On s'assure que config_data est compatible avec ProviderConfig
    # Note: config_data devrait être validé par ProviderConfig avant d'arriver ici
    providers_data[provider_id] = config_data

    # 3. Sauvegarder
    data["providers"] = providers_data
    with open(_PROVIDERS_YAML, "w", encoding="utf-8") as f:
        yaml.dump(data, f, sort_keys=False, allow_unicode=True)

    # 4. Invalider le cache mémoire pour forcer le rechargement
    _providers_cache = None


def delete_provider_config(provider_id: str) -> None:
    """Supprime la configuration d'un provider de providers.yaml."""
    global _providers_cache

    try:
        with open(_PROVIDERS_YAML, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return

    providers_data = data.get("providers", {}) or {}
    if provider_id in providers_data:
        del providers_data[provider_id]
        data["providers"] = providers_data
        with open(_PROVIDERS_YAML, "w", encoding="utf-8") as f:
            yaml.dump(data, f, sort_keys=False, allow_unicode=True)
        _providers_cache = None


def get_provider_config(provider_id: str) -> ProviderConfig | None:
    """Récupère la config d'un provider par son ID."""
    _load_providers_yaml()
    return _providers_cache.get(provider_id) if _providers_cache else None


def list_providers(enabled_only: bool = True) -> list[ProviderConfig]:
    """Liste tous les providers configurés."""
    _load_providers_yaml()
    if not _providers_cache:
        return []
    providers = list(_providers_cache.values())
    if enabled_only:
        providers = [p for p in providers if p.enabled]
    return providers


def get_provider_for_model(model_provider: str) -> ProviderConfig | None:
    """Récupère le provider pour un modèle (par provider ID)."""
    return get_provider_config(model_provider)


def resolve_base_url(provider: ProviderConfig) -> str:
    """Résout l'URL de base du provider avec variables d'env."""
    # 1. Valeur explicite
    if provider.base_url:
        return provider.base_url

    # 2. Template avec variables (ex: Cloudflare)
    if provider.base_url_template:
        vars_resolved = {}
        for var_name, env_var in provider.base_url_vars.items():
            value = os.getenv(env_var, "").strip()
            if not value:
                raise ValueError(
                    f"Variable d'env '{env_var}' requise pour provider '{provider.id}' "
                    f"(variable template '{var_name}')"
                )
            vars_resolved[var_name] = value
        return provider.base_url_template.format(**vars_resolved)

    # 3. Env var directe
    if provider.base_url_env:
        value = os.getenv(provider.base_url_env, "").strip()
        if value:
            return value

    # 4. Défaut
    if provider.base_url_default:
        return provider.base_url_default

    raise ValueError(f"Pas de base_url configurée pour provider '{provider.id}'")


def resolve_auth_headers(provider: ProviderConfig) -> dict[str, str]:
    """Résout les headers d'authentification."""
    headers = {}
    auth = provider.auth

    if auth.type == "none":
        return headers

    # 1. Valeur explicite
    api_key = auth.api_key

    # 2. Variable d'env
    if not api_key and auth.api_key_env:
        api_key = os.getenv(auth.api_key_env, "").strip()

    if api_key:
        if auth.type == "bearer":
            headers["Authorization"] = f"Bearer {api_key}"
        elif auth.type == "x-api-key":
            headers["x-api-key"] = api_key
        elif auth.type == "custom":
            # Pour custom, on attend que extra_headers contienne le pattern
            pass
    elif auth.required:
        raise ValueError(
            f"Clé API requise pour provider '{provider.id}': "
            f"ni valeur explicite, ni variable d'env '{auth.api_key_env}'"
        )

    # Headers additionnels statiques
    headers.update(provider.extra_headers)

    # Headers additionnels depuis env (JSON)
    if provider.extra_headers_env:
        extra_json = os.getenv(provider.extra_headers_env, "").strip()
        if extra_json:
            try:
                extra_headers = json.loads(extra_json)
                if isinstance(extra_headers, dict):
                    headers.update(extra_headers)
            except json.JSONDecodeError:
                pass

    return headers


def validate_provider_for_model(provider: ProviderConfig, model_name: str) -> bool:
    """Vérifie que le provider supporte le modèle (si liste non vide)."""
    if not provider.supported_models:
        return True  # Pas de restriction
    return model_name in provider.supported_models


__all__ = [
    "ProviderConfig",
    "ProviderAuth",
    "get_provider_config",
    "list_providers",
    "get_provider_for_model",
    "resolve_base_url",
    "resolve_auth_headers",
    "validate_provider_for_model",
    "save_provider_config",
    "delete_provider_config",
]