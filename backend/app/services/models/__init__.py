# Models Package — Model Gateway Infrastructure
"""
Model Gateway, Registry, Resolver — abstraction des providers LLM.

Architecture :
  Application → Model Registry → Model Resolver → Model Gateway → LLM

Logical model IDs : default, coding, research, fast, reasoning, vision
Providers : ollama, openai, anthropic, etc. (configurables par admin via providers.yaml)
"""

from app.services.models.schemas import ModelConfig, ModelAssignment, ModelPurposeResult
from app.services.models.registry import (
    get_model_config,
    list_all_model_configs,
    save_model_config,
    delete_model_config,
    get_default_model_id,
)
from app.services.models.resolver import (
    resolve_model_for_purpose,
    get_model_for_subgraph,
    set_global_assignment,
    get_global_assignment,
)
from app.services.models.provider_registry import (
    get_provider_config,
    list_providers,
    resolve_base_url,
    resolve_auth_headers,
)
from app.services.models.client_factory import (
    get_llm_client,
    get_unified_client,
    UnifiedLLMClient,
    invalidate_client_cache,
)

__all__ = [
    # Schemas
    "ModelConfig",
    "ModelAssignment",
    "ModelPurposeResult",
    # Registry
    "get_model_config",
    "list_all_model_configs",
    "save_model_config",
    "delete_model_config",
    "get_default_model_id",
    # Resolver
    "resolve_model_for_purpose",
    "get_model_for_subgraph",
    "set_global_assignment",
    "get_global_assignment",
    # Provider Registry
    "get_provider_config",
    "list_providers",
    "resolve_base_url",
    "resolve_auth_headers",
    # Client Factory
    "get_llm_client",
    "get_unified_client",
    "UnifiedLLMClient",
    "invalidate_client_cache",
]
