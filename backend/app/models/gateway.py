# Model Gateway — Abstraction des providers LLM (§5)
#
# Le gateway fournit une interface unifiée pour instancier des LLMs
# via LiteLLM Proxy ou directement via LangChain.
#
# Architecture :
#   Application → Model Gateway → LiteLLM Proxy → Provider
#                                    ↓
#                              Ollama/OpenAI/Anthropic/etc.
#
# Utilisation :
#   llm = get_llm_for_purpose("coding", user_id="user_123")
#
# Contrat (mission §1/§6/§7) :
#   - instanciation UNIQUE ici (jamais de ChatOllama dans le business
#     logic) — toujours APRÈS une résolution registry→resolver
#   - AUCUN secret en dur : clé absente → erreur explicite
#   - un modèle désactivé ou sans capacités requises n'est JAMAIS
#     instancié (résolution is_enabled=False → ModelGatewayError)
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel

from app.config import (
    MODEL_PROVIDER_RETRIES,
    MODEL_REQUEST_TIMEOUT_SECONDS,
    OLLAMA_HOST,
    ollama_headers,
)


class ModelGatewayError(RuntimeError):
    """Erreur contrôlée du Model Gateway (résolution/instanciation)."""


def get_llm_for_purpose(
    purpose: str = "default",
    user_id: str | None = None,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    path: Path | None = None,
) -> BaseChatModel:
    """Obtient un LLM configuré pour un purpose donné.

    Utilise le Model Resolver (registry→resolver) pour déterminer le
    modèle, puis instancie le LLM via le provider idoine. Un modèle
    désactivé/sans capacités requises/inconnu → ModelGatewayError
    explicite (jamais de silence, jamais de config bidon).

    Args:
        purpose: default, coding, research, fast, reasoning, vision
        user_id: ID utilisateur pour résolution personnalisée
        temperature: température du modèle (0.0 par défaut)
        max_tokens: tokens max de sortie
        path: registry YAML (tests)

    Returns:
        BaseChatModel configuré
    """
    from app.models.resolver import resolve_model_for_purpose

    result = resolve_model_for_purpose(
        purpose=purpose, user_id=user_id, path=path
    )

    if not result.is_enabled or result.config is None:
        raise ModelGatewayError(
            f"Modèle indisponible pour purpose='{purpose}' : {result.reason}"
        )

    config = result.config

    # LiteLLM : uniquement si explicitement activé ET clé configurée.
    litellm_enabled = os.getenv("MODEL_GATEWAY_ENABLED", "false").lower() == "true"
    litellm_base_url = os.getenv("LITELLM_BASE_URL", "")

    if litellm_enabled:
        if not litellm_base_url:
            raise ModelGatewayError(
                "MODEL_GATEWAY_ENABLED=true mais LITELLM_BASE_URL absent"
            )
        return _get_litellm_llm(
            config,
            base_url=litellm_base_url,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    return _get_direct_llm(
        config,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _get_litellm_llm(
    config: Any,
    base_url: str,
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> BaseChatModel:
    """Instancie un LLM via LiteLLM Proxy (OpenAI-compatible)."""
    from langchain_openai import ChatOpenAI

    api_key = os.getenv("LITELLM_API_KEY", "")
    if not api_key:
        raise ModelGatewayError(
            "LITELLM_API_KEY absent — clé requise pour le provider distant"
        )

    # Modèle à passer à LiteLLM : soit gateway_model, soit model_name
    model = config.gateway_model or config.model_name

    return ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=MODEL_REQUEST_TIMEOUT_SECONDS,
        max_retries=MODEL_PROVIDER_RETRIES,
    )


def _get_direct_llm(
    config: Any,
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> BaseChatModel:
    """Instancie un LLM directement selon le provider."""
    provider = config.provider.lower()
    model_name = config.model_name

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        headers = ollama_headers()
        client_kwargs: dict = {"timeout": MODEL_REQUEST_TIMEOUT_SECONDS}
        if headers:
            client_kwargs["headers"] = headers

        return ChatOllama(
            model=model_name,
            base_url=OLLAMA_HOST,
            temperature=temperature,
            num_predict=max_tokens or config.max_output_tokens,
            client_kwargs=client_kwargs,
        )

    elif provider == "openai":
        from langchain_openai import ChatOpenAI

        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise ModelGatewayError("OPENAI_API_KEY non configuré")

        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=MODEL_REQUEST_TIMEOUT_SECONDS,
            max_retries=MODEL_PROVIDER_RETRIES,
        )

    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ModelGatewayError("ANTHROPIC_API_KEY non configuré")

        return ChatAnthropic(
            model=model_name,
            anthropic_api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens or config.max_output_tokens,
            timeout=MODEL_REQUEST_TIMEOUT_SECONDS,
            max_retries=MODEL_PROVIDER_RETRIES,
        )

    raise ModelGatewayError(
        f"Provider inconnu '{provider}' pour le modèle '{model_name}' — "
        "configurer le provider côté admin (jamais de fallback silencieux)"
    )


def create_llm_from_config(
    model_id: str,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    path: Path | None = None,
) -> BaseChatModel:
    """Crée un LLM depuis un model_id explicite (admin override).

    Un modèle inconnu OU désactivé → ModelGatewayError explicite
    (le champ `enabled` du registry est RESPECTÉ au point d'usage).
    """
    from app.models.registry import get_model_config

    config = get_model_config(model_id, path=path)
    if not config:
        raise ModelGatewayError(f"Modèle {model_id} non configuré")

    if not config.enabled:
        raise ModelGatewayError(f"Modèle {model_id} désactivé")

    return _get_direct_llm(
        config, temperature=temperature, max_tokens=max_tokens
    )


__all__ = [
    "ModelGatewayError",
    "get_llm_for_purpose",
    "create_llm_from_config",
]
