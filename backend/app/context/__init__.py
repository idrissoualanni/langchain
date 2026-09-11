# Package context — Context Engineering (V5)
#
#   schemas.py        → schémas structurés centralisés (§11/§14/§30)
#   router            → RoutingResult pydantic (classification)
#   build_context()   → BuiltContext (sélection multi-sources)
#   prompt_builder    → présentation uniquement (§35)
#
# Architecture V5 (§72) :
#   ROUTER + SUBJECT REGISTRY + KNOWLEDGE + TOOLS + USER MEMORY
#   + THREAD STATE (+ LEARNING réservé V6+) → BUILDER →
#   DYNAMIC PROMPT (@dynamic_prompt natif) → MODEL
from app.context.builder import (
    build_context,
    build_system_prompt,
    build_thread_context,
    build_user_context,
)
from app.context.prompt_builder import build_system_prompt  # noqa: F811
from app.context.router import route_subject
from app.context.schemas import (  # noqa: F401
    AgentContext,
    BuiltContext,
    KnowledgeResult,
    KnowledgeSearchResult,
    ResolvedTools,
    RoutingResult,
)

__all__ = [
    "build_context",
    "build_system_prompt",
    "build_thread_context",
    "build_user_context",
    "route_subject",
    "AgentContext",
    "BuiltContext",
    "KnowledgeResult",
    "KnowledgeSearchResult",
    "ResolvedTools",
    "RoutingResult",
]
