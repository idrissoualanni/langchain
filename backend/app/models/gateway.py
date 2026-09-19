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
from __future__ import annotations

import os
from typing import Any

from langchain_core.language_models import BaseChatModel


def get_llm_for_purpose(
    purpose: str = "default",
    user_id: str | None = None,
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> BaseChatModel:
    """Obtient un LLM configuré pour un purpose donné.
    
    Utilise le Model Resolver pour déterminer le modèle, puis
    instancie le LLM via le gateway approprié (LiteLLM ou direct).
    
    Args:
        purpose: default, coding, research, fast, reasoning, vision
        user_id: ID utilisateur pour résolution personnalisée
        temperature: température du modèle (0.0 par défaut)
        max_tokens: tokens max de sortie
    
    Returns:
        BaseChatModel configuré
    """
    from app.models.resolver import resolve_model_for_purpose
    
    result = resolve_model_for_purpose(purpose=purpose, user_id=user_id)
    
    if not result.config:
        # Fallback sur modèle par défaut
        from app.config import MODEL_NAME, OLLAMA_HOST
        from langchain_ollama import ChatOllama
        
        return ChatOllama(
            model=MODEL_NAME,
            base_url=OLLAMA_HOST,
            temperature=temperature,
        )
    
    config = result.config
    
    # Vérifier si LiteLLM est activé
    litellm_enabled = os.getenv("MODEL_GATEWAY_ENABLED", "false").lower() == "true"
    litellm_base_url = os.getenv("LITELLM_BASE_URL", "")
    
    if litellm_enabled and litellm_base_url:
        return _get_litellm_llm(
            model_config=config,
            base_url=litellm_base_url,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    
    # Fallback : provider direct
    return _get_direct_llm(
        model_config=config,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _get_litellm_llm(
    model_config: Any,
    base_url: str,
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> BaseChatModel:
    """Instancie un LLM via LiteLLM Proxy (OpenAI-compatible)."""
    from langchain_openai import ChatOpenAI
    
    api_key = os.getenv("LITELLM_API_KEY", "sk-litellm-placeholder")
    
    # Modèle à passer à LiteLLM : soit gateway_model, soit model_name
    model = model_config.gateway_model or model_config.model_name
    
    return ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _get_direct_llm(
    model_config: Any,
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> BaseChatModel:
    """Instancie un LLM directement selon le provider."""
    provider = model_config.provider.lower()
    model_name = model_config.model_name
    
    if provider == "ollama":
        from langchain_ollama import ChatOllama
        from app.config import OLLAMA_HOST, ollama_headers
        
        headers = ollama_headers()
        client_kwargs = {"headers": headers} if headers else None
        
        return ChatOllama(
            model=model_name,
            base_url=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            temperature=temperature,
            max_tokens=max_tokens or model_config.max_output_tokens,
            client_kwargs=client_kwargs,
        )
    
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OPENAI_API_KEY non configuré")
        
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY non configuré")
        
        return ChatAnthropic(
            model=model_name,
            anthropic_api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens or model_config.max_output_tokens,
        )
    
    else:
        # Fallback Ollama pour providers inconnus
        from langchain_ollama import ChatOllama
        from app.config import OLLAMA_HOST
        
        return ChatOllama(
            model=model_name,
            base_url=OLLAMA_HOST,
            temperature=temperature,
        )


def create_llm_from_config(
    model_id: str,
    temperature: float = 0.0,
    max_tokens: int | None = None,
) -> BaseChatModel:
    """Crée un LLM depuis un model_id explicite.
    
    Utile pour les tests de configuration admin.
    """
    from app.models.registry import get_model_config
    
    config = get_model_config(model_id)
    if not config:
        raise ValueError(f"Modèle {model_id} non configuré")
    
    if not config.enabled:
        raise ValueError(f"Modèle {model_id} désactivé")
    
    return _get_direct_llm(config, temperature=temperature, max_tokens=max_tokens)


__all__ = [
    "get_llm_for_purpose",
    "create_llm_from_config",
]
