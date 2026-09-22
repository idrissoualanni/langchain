# Model Gateway — Infrastructure Layer (§4-§10)
#
# Abstraction des providers LLM via LiteLLM Proxy ou équivalent.
# Le code applicatif utilise des logical model IDs (default, coding,
# research, fast, reasoning, vision) — le provider réel est une
# configuration d'infrastructure administrable.
#
# Architecture :
#   Application → Model Registry → Model Resolver → Model Gateway → LLM
#
# Jamais de ChatOllama/ChatOpenAI dispersés dans le business logic.
from __future__ import annotations

import os
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.model_capabilities import ModelCapabilities


class ModelConfig(BaseModel):
    """Configuration d'un modèle dans le registry (§6).
    
    id            : identifiant logique (default, coding, research...)
    display_name  : nom lisible pour l'admin
    provider      : ollama, openai, anthropic, etc.
    model_name    : nom technique du modèle (ex: qwen2.5, gpt-4o)
    gateway_model : alias gateway si différent de model_name
    enabled       : modèle activé pour usage
    context_window: fenêtre de contexte (null = inconnue)
    max_output_tokens: tokens max sortie
    capabilities  : capacités du modèle (tools, vision, etc.)
    metadata      : métadonnées admin (version, notes, etc.)
    """
    
    id: str
    display_name: str = ""
    provider: str = "ollama"
    model_name: str = "default"
    gateway_model: str | None = None
    enabled: bool = True
    context_window: int | None = None
    max_output_tokens: int | None = None
    capabilities: ModelCapabilities = Field(
        default_factory=ModelCapabilities
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelAssignment(BaseModel):
    """Assignment d'un modèle à un scope (§9).
    
    scope    : global, group, user
    target   : id de la cible (vide si global)
    purpose  : usage visé (default, coding, research, fast, reasoning, vision)
    model_id : modèle logique assigné
    priority : priorité de résolution (user > group > global)
    """
    
    scope: Literal["global", "group", "user"] = "global"
    target: str = ""
    purpose: Literal[
        "default", "coding", "research", "fast", "reasoning", "vision"
    ] = "default"
    model_id: str = "default"
    priority: int = 0  # user=100, group=50, global=0


class ModelPurposeResult(BaseModel):
    """Résultat de résolution de modèle par purpose."""
    
    model_id: str
    config: ModelConfig | None = None
    resolved_from: str = "unknown"  # user, group, global, fallback
    is_enabled: bool = False
    reason: str = ""


__all__ = [
    "ModelConfig",
    "ModelAssignment", 
    "ModelPurposeResult",
]
