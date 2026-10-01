# Client Factory — Fabrique de clients LLM selon provider
#
# Utilise ProviderRegistry pour créer le bon client (OpenAI, Ollama, Anthropic, custom).
# Le code applicatif n'importe QUE get_llm_client() et appelle .chat_completion().

from __future__ import annotations

import importlib
import json
from typing import Any

from openai import AsyncOpenAI, OpenAI

from app.services.models.provider_registry import (
    ProviderConfig,
    get_provider_config,
    resolve_base_url,
    resolve_auth_headers,
    validate_provider_for_model,
)
from app.services.models.registry import get_model_config
from app.services.models.schemas import ModelConfig


# ──────────────────────────────────────────────────────────────
# Clients par type de provider
# ──────────────────────────────────────────────────────────────

class BaseLLMClient:
    """Interface commune pour tous les clients LLM."""
    
    def __init__(self, provider: ProviderConfig, model_config: ModelConfig):
        self.provider = provider
        self.model_config = model_config
        self.model_name = model_config.model_name
    
    def chat_completion(self, messages: list[dict], **kwargs) -> Any:
        raise NotImplementedError
    
    async def achat_completion(self, messages: list[dict], **kwargs) -> Any:
        raise NotImplementedError
    
    def embeddings(self, texts: list[str], **kwargs) -> Any:
        raise NotImplementedError
    
    async def aembeddings(self, texts: list[str], **kwargs) -> Any:
        raise NotImplementedError


class OpenAICompatibleClient(BaseLLMClient):
    """Client pour APIs compatibles OpenAI (OpenAI, Cloudflare, Together, etc.)."""
    
    def __init__(self, provider: ProviderConfig, model_config: ModelConfig):
        super().__init__(provider, model_config)
        base_url = resolve_base_url(provider)
        # Ajouter api_path si présent
        if provider.api_path:
            base_url = base_url.rstrip("/") + provider.api_path
        
        headers = resolve_auth_headers(provider)
        
        self._sync_client = OpenAI(
            base_url=base_url,
            api_key="dummy",  # L'auth est dans les headers
            default_headers=headers,
            timeout=provider.timeout_seconds,
            max_retries=provider.max_retries,
        )
        self._async_client = AsyncOpenAI(
            base_url=base_url,
            api_key="dummy",
            default_headers=headers,
            timeout=provider.timeout_seconds,
            max_retries=provider.max_retries,
        )
    
    def chat_completion(self, messages: list[dict], **kwargs) -> Any:
        return self._sync_client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            **kwargs
        )
    
    async def achat_completion(self, messages: list[dict], **kwargs) -> Any:
        return await self._async_client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            **kwargs
        )
    
    def embeddings(self, texts: list[str], **kwargs) -> Any:
        return self._sync_client.embeddings.create(
            model=self.model_name,
            input=texts,
            **kwargs
        )
    
    async def aembeddings(self, texts: list[str], **kwargs) -> Any:
        return await self._async_client.embeddings.create(
            model=self.model_name,
            input=texts,
            **kwargs
        )


class OllamaClient(BaseLLMClient):
    """Client pour API Ollama native (utilise aussi OpenAI client sur /v1)."""
    
    def __init__(self, provider: ProviderConfig, model_config: ModelConfig):
        super().__init__(provider, model_config)
        base_url = resolve_base_url(provider)
        if provider.api_path:
            base_url = base_url.rstrip("/") + provider.api_path
        
        headers = resolve_auth_headers(provider)
        
        self._sync_client = OpenAI(
            base_url=base_url,
            api_key="ollama",  # Ollama ignore la clé
            default_headers=headers,
            timeout=provider.timeout_seconds,
            max_retries=provider.max_retries,
        )
        self._async_client = AsyncOpenAI(
            base_url=base_url,
            api_key="ollama",
            default_headers=headers,
            timeout=provider.timeout_seconds,
            max_retries=provider.max_retries,
        )
    
    def chat_completion(self, messages: list[dict], **kwargs) -> Any:
        return self._sync_client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            **kwargs
        )
    
    async def achat_completion(self, messages: list[dict], **kwargs) -> Any:
        return await self._async_client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            **kwargs
        )
    
    def embeddings(self, texts: list[str], **kwargs) -> Any:
        return self._sync_client.embeddings.create(
            model=self.model_name,
            input=texts,
            **kwargs
        )
    
    async def aembeddings(self, texts: list[str], **kwargs) -> Any:
        return await self._async_client.embeddings.create(
            model=self.model_name,
            input=texts,
            **kwargs
        )


class AnthropicClient(BaseLLMClient):
    """Client pour API Anthropic native."""
    
    def __init__(self, provider: ProviderConfig, model_config: ModelConfig):
        super().__init__(provider, model_config)
        try:
            from anthropic import Anthropic, AsyncAnthropic
        except ImportError:
            raise RuntimeError(
                "Package 'anthropic' requis pour provider Anthropic. "
                "Installez-le: pip install anthropic"
            )
        
        base_url = resolve_base_url(provider)
        headers = resolve_auth_headers(provider)
        
        # Anthropic utilise x-api-key header
        api_key = headers.get("x-api-key") or headers.get("authorization", "").replace("Bearer ", "")
        
        self._sync_client = Anthropic(
            base_url=base_url,
            api_key=api_key,
            default_headers=headers,
            timeout=provider.timeout_seconds,
            max_retries=provider.max_retries,
        )
        self._async_client = AsyncAnthropic(
            base_url=base_url,
            api_key=api_key,
            default_headers=headers,
            timeout=provider.timeout_seconds,
            max_retries=provider.max_retries,
        )
    
    def _convert_messages(self, messages: list[dict]) -> tuple[str, list[dict]]:
        """Convertit messages OpenAI format → Anthropic format."""
        system = ""
        anthropic_messages = []
        
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            
            if role == "system":
                system = content
            elif role == "user":
                anthropic_messages.append({"role": "user", "content": content})
            elif role == "assistant":
                anthropic_messages.append({"role": "assistant", "content": content})
            elif role == "tool":
                # Tool results → user message avec tool_result
                anthropic_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.get("tool_call_id", ""),
                            "content": content,
                        }
                    ]
                })
        
        return system, anthropic_messages
    
    def chat_completion(self, messages: list[dict], **kwargs) -> Any:
        system, anthropic_messages = self._convert_messages(messages)
        
        # Gérer tools si présents
        tools = kwargs.pop("tools", None)
        tool_choice = kwargs.pop("tool_choice", None)
        
        response = self._sync_client.messages.create(
            model=self.model_name,
            system=system,
            messages=anthropic_messages,
            tools=tools,
            tool_choice=tool_choice,
            **kwargs
        )
        
        # Convertir réponse Anthropic → format OpenAI-like
        return self._to_openai_format(response)
    
    async def achat_completion(self, messages: list[dict], **kwargs) -> Any:
        system, anthropic_messages = self._convert_messages(messages)
        tools = kwargs.pop("tools", None)
        tool_choice = kwargs.pop("tool_choice", None)
        
        response = await self._async_client.messages.create(
            model=self.model_name,
            system=system,
            messages=anthropic_messages,
            tools=tools,
            tool_choice=tool_choice,
            **kwargs
        )
        return self._to_openai_format(response)
    
    def _to_openai_format(self, response) -> Any:
        """Convertit réponse Anthropic → format compatible OpenAI."""
        # Créer un objet compatible avec .choices[0].message.content
        class Choice:
            def __init__(self, message):
                self.message = message
        
        class Message:
            def __init__(self, content, tool_calls=None):
                self.content = content
                self.tool_calls = tool_calls
                self.role = "assistant"
        
        content = ""
        tool_calls = None
        
        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                if tool_calls is None:
                    tool_calls = []
                tool_calls.append({
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": json.dumps(block.input)
                    }
                })
        
        message = Message(content=content, tool_calls=tool_calls)
        return type("Response", (), {"choices": [Choice(message)]})()
    
    def embeddings(self, texts: list[str], **kwargs) -> Any:
        raise NotImplementedError("Anthropic n'a pas d'API embeddings native")
    
    async def aembeddings(self, texts: list[str], **kwargs) -> Any:
        raise NotImplementedError("Anthropic n'a pas d'API embeddings native")


class CustomClient(BaseLLMClient):
    """Client personnalisé importé dynamiquement."""
    
    def __init__(self, provider: ProviderConfig, model_config: ModelConfig):
        super().__init__(provider, model_config)
        
        if not provider.client_class:
            raise ValueError(f"Provider '{provider.id}' de type 'custom' sans client_class")
        
        # Import dynamique: "module.path.ClassName"
        module_path, class_name = provider.client_class.rsplit(".", 1)
        module = importlib.import_module(module_path)
        client_class = getattr(module, class_name)
        
        # Instancier avec la config du provider
        self._client = client_class(
            provider=provider,
            model_config=model_config,
            **provider.client_config
        )
    
    def chat_completion(self, messages: list[dict], **kwargs) -> Any:
        return self._client.chat_completion(messages, **kwargs)
    
    async def achat_completion(self, messages: list[dict], **kwargs) -> Any:
        return await self._client.achat_completion(messages, **kwargs)
    
    def embeddings(self, texts: list[str], **kwargs) -> Any:
        return self._client.embeddings(texts, **kwargs)
    
    async def aembeddings(self, texts: list[str], **kwargs) -> Any:
        return await self._client.aembeddings(texts, **kwargs)


# ──────────────────────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────────────────────

_CLIENT_CACHE: dict[str, BaseLLMClient] = {}


def _create_client(provider: ProviderConfig, model_config: ModelConfig) -> BaseLLMClient:
    """Crée le client approprié selon le type de provider."""
    provider_type = provider.type.lower()
    
    if provider_type == "openai_compatible":
        return OpenAICompatibleClient(provider, model_config)
    elif provider_type == "ollama":
        return OllamaClient(provider, model_config)
    elif provider_type == "anthropic":
        return AnthropicClient(provider, model_config)
    elif provider_type == "custom":
        return CustomClient(provider, model_config)
    else:
        raise ValueError(f"Type de provider inconnu: {provider_type}")


def get_llm_client(model_id: str) -> BaseLLMClient:
    """
    Récupère (ou crée) le client LLM pour un modèle logique.
    
    Utilise le cache pour réutiliser les clients (thread-safe pour lecture).
    """
    if model_id in _CLIENT_CACHE:
        return _CLIENT_CACHE[model_id]
    
    # 1. Récupérer la config du modèle
    model_config = get_model_config(model_id)
    if model_config is None:
        raise ValueError(f"Modèle '{model_id}' introuvable dans le registry")
    
    # 2. Récupérer la config du provider
    provider = get_provider_config(model_config.provider)
    if provider is None:
        raise ValueError(f"Provider '{model_config.provider}' introuvable pour modèle '{model_id}'")
    
    if not provider.enabled:
        raise RuntimeError(f"Provider '{provider.id}' désactivé (enabled=false)")
    
    # 3. Valider que le provider supporte ce modèle
    if not validate_provider_for_model(provider, model_config.model_name):
        raise ValueError(
            f"Modèle '{model_config.model_name}' non supporté par provider '{provider.id}'"
        )
    
    # 4. Créer et cacher le client
    client = _create_client(provider, model_config)
    _CLIENT_CACHE[model_id] = client
    return client


def invalidate_client_cache(model_id: str | None = None) -> None:
    """Invalide le cache (utile après modification config)."""
    global _CLIENT_CACHE
    if model_id:
        _CLIENT_CACHE.pop(model_id, None)
    else:
        _CLIENT_CACHE.clear()


# ──────────────────────────────────────────────────────────────
# Interface unifiée pour le code applicatif
# ──────────────────────────────────────────────────────────────

class UnifiedLLMClient:
    """
    Facade unifiée — le code appelant n'utilise QUE cette classe.
    
    Usage:
        client = UnifiedLLMClient()
        response = client.chat_completion("coding", messages, tools=...)
        # ou avec modèle explicite:
        response = client.chat_completion_for_model("cf-llama-3.1-8b", messages)
    """
    
    def chat_completion(
        self,
        purpose_or_model: str,
        messages: list[dict],
        user_id: str | None = None,
        **kwargs
    ) -> Any:
        """
        Appel chat completion par purpose (résout le modèle) ou modèle explicite.
        
        Args:
            purpose_or_model: purpose (coding, research...) OU model_id explicite
            messages: Messages format OpenAI
            user_id: Pour résolution user-specific
            **kwargs: Args passés au client (tools, temperature, etc.)
        """
        from app.services.models.resolver import resolve_model_for_purpose
        
        # Détecter si c'est un purpose ou un model_id
        model_config = get_model_config(purpose_or_model)
        
        if model_config and model_config.enabled:
            # C'est un model_id explicite
            model_id = purpose_or_model
        else:
            # C'est un purpose → résoudre
            result = resolve_model_for_purpose(
                purpose=purpose_or_model,
                user_id=user_id,
            )
            if not result.is_enabled:
                raise RuntimeError(f"Aucun modèle disponible pour purpose '{purpose_or_model}': {result.reason}")
            model_id = result.model_id
        
        client = get_llm_client(model_id)
        return client.chat_completion(messages, **kwargs)
    
    async def achat_completion(
        self,
        purpose_or_model: str,
        messages: list[dict],
        user_id: str | None = None,
        **kwargs
    ) -> Any:
        """Version async."""
        from app.services.models.resolver import resolve_model_for_purpose
        
        model_config = get_model_config(purpose_or_model)
        
        if model_config and model_config.enabled:
            model_id = purpose_or_model
        else:
            result = resolve_model_for_purpose(
                purpose=purpose_or_model,
                user_id=user_id,
            )
            if not result.is_enabled:
                raise RuntimeError(f"Aucun modèle disponible pour purpose '{purpose_or_model}': {result.reason}")
            model_id = result.model_id
        
        client = get_llm_client(model_id)
        return await client.achat_completion(messages, **kwargs)
    
    def chat_completion_for_model(
        self,
        model_id: str,
        messages: list[dict],
        **kwargs
    ) -> Any:
        """Appel direct avec model_id explicite (bypass resolver)."""
        client = get_llm_client(model_id)
        return client.chat_completion(messages, **kwargs)
    
    async def achat_completion_for_model(
        self,
        model_id: str,
        messages: list[dict],
        **kwargs
    ) -> Any:
        client = get_llm_client(model_id)
        return await client.achat_completion(messages, **kwargs)
    
    def embeddings(self, model_id: str, texts: list[str], **kwargs) -> Any:
        """Appel embeddings pour un modèle donné."""
        client = get_llm_client(model_id)
        return client.embeddings(texts, **kwargs)
    
    async def aembeddings(self, model_id: str, texts: list[str], **kwargs) -> Any:
        client = get_llm_client(model_id)
        return await client.aembeddings(texts, **kwargs)


# Singleton pour usage simple
_unified_client: UnifiedLLMClient | None = None


def get_unified_client() -> UnifiedLLMClient:
    """Retourne le client unifié singleton."""
    global _unified_client
    if _unified_client is None:
        _unified_client = UnifiedLLMClient()
    return _unified_client


__all__ = [
    "BaseLLMClient",
    "OpenAICompatibleClient",
    "OllamaClient",
    "AnthropicClient",
    "CustomClient",
    "get_llm_client",
    "invalidate_client_cache",
    "UnifiedLLMClient",
    "get_unified_client",
]