# SHIM de compatibilité (refactor — phase migration).
#
# Les contrats contexte ont déménagé vers app/schemas/context.py.
# SUPPRESSION prévue phase cleanup (§30 mission) après vérification.
from app.schemas.context import (
    ActivityContextInfo,
    AgentContext,
    BuiltContext,
    ContextStats,
    DocumentContextInfo,
    FallbackDecision,
    KnowledgeResult,
    KnowledgeSearchResult,
    ResolvedTools,
    RoutingResult,
    SearchResponse,
    SearchResult,
    SubjectContextInfo,
    ThreadContextInfo,
    UserContextInfo,
)

__all__ = [
    "AgentContext",
    "RoutingResult",
    "SearchResult",
    "SearchResponse",
    "FallbackDecision",
    "KnowledgeResult",
    "KnowledgeSearchResult",
    "ResolvedTools",
    "ActivityContextInfo",
    "SubjectContextInfo",
    "UserContextInfo",
    "ThreadContextInfo",
    "ContextStats",
    "BuiltContext",
]
