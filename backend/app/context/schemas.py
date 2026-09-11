# Context Schemas V5 — schémas structurés CENTRALISÉS (§11/§14/§30).
#
# Séparation LangChain native vs business logic :
#   - Runtime Context  = DONNÉES D'EXÉCUTION (user_id, thread_id) —
#     transporté par le mécanisme officiel context= de create_agent,
#     PAS injecté dans le prompt ni passé via configurable.
#   - RoutingResult    = sortie VALIDÉE du router (pydantic, §14)
#   - KnowledgeResult  = item knowledge structuré (§24)
#   - BuiltContext     = contexte métier assemblé par le Context
#     Builder (§30) — sélectionné puis présenté par le Prompt Builder.
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ------------------------------------------------------------------
# Runtime Context (§4/§5) — user_id/thread_id en DI native LangChain
# ------------------------------------------------------------------


@dataclass
class AgentContext:
    """Contexte d'exécution transporté par LangGraph Runtime.

    Transmis via agent.invoke(..., context=AgentContext(...)) —
    accessible dans middleware/tools via request.runtime.context /
    runtime.context. Jamais injecté tel quel dans le prompt (§36).

    user_id   : identité persistante — isole le Store mémoire
    thread_id : conversation courante (redondant avec le
                configurable du checkpointer, mais disponible pour
                les outils/middleware sans get_config()).
    """

    user_id: str = ""
    thread_id: str = ""


# ------------------------------------------------------------------
# Routing (§14) — sortie structurée validée du router
# ------------------------------------------------------------------


class RoutingResult(BaseModel):
    """Résultat de classification d'une question par le router.

    Le router répond UNIQUEMENT à « de quoi parle la demande ? »
    (§15) — jamais quelle réponse donner.
    """

    status: Literal[
        "supported",
        "ambiguous",
        "unsupported",
        "unknown",
        "multi_domain",
    ] = Field(
        description="Statut du routing : supported (matière "
        "configurée), ambiguous (plusieurs interprétations), "
        "unsupported (matière détectée non configurée), unknown "
        "(rien d'identifié), multi_domain (domaines multiples)"
    )
    subject: str | None = Field(
        default=None,
        description="id de la matière si détectée (ex: python)",
    )
    topic: str | None = Field(
        default=None,
        description="topic si identifiable (ex: return)",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confiance du routing [0..1]",
    )
    candidates: list[str] = Field(
        default_factory=list,
        description="Matières candidates si ambiguous",
    )
    subjects: list[str] = Field(
        default_factory=list,
        description="Matières des domaines si multi_domain",
    )


# ------------------------------------------------------------------
# Knowledge (§24) — item de connaissance structuré
# ------------------------------------------------------------------


class KnowledgeResult(BaseModel):
    """Une section knowledge pertinente récupérée pour le run."""

    source: str = Field(
        description="Chemin source (ex: python/functions)",
    )
    topic: str = Field(
        description="Topic de la section (ex: return)",
    )
    content: str = Field(
        description="Contenu de la section du cours",
    )
    relevance: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Score de pertinence [0..1]",
    )


class KnowledgeSearchResult(BaseModel):
    """Résultat complet d'une recherche knowledge (§38)."""

    status: Literal["found", "insufficient", "unavailable"] = (
        Field(
            default="unavailable",
            description="found : sections pertinentes trouvées ; "
            "insufficient : sources parcourues mais rien de "
            "pertinent ; unavailable : aucune source disponible",
        )
    )
    items: list[KnowledgeResult] = Field(default_factory=list)
    searched_sources: int = Field(
        default=0,
        description="Nombre de sources knowledge parcourues",
    )


# ------------------------------------------------------------------
# Tools (§28/§39) — résolution des tools disponibles
# ------------------------------------------------------------------


class ResolvedTools(BaseModel):
    """Tools réellement disponibles pour un run (resolve_tools).

    available     : tools IMPLÉMENTÉS fournis au modèle
    declared      : tools déclarés dans le SubjectConfig
    unavailable   : tools déclarés mais NON enregistrés (§39 :
                    loggés, jamais exposés au modèle)
    """

    available: list[str] = Field(default_factory=list)
    declared: list[str] = Field(default_factory=list)
    unavailable: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------
# Context priorité + budget (§40/§41) — préparation V5+
# ------------------------------------------------------------------


class ContextPriority(str, Enum):
    """Priorité d'une source de contexte (budget futur)."""

    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


# ------------------------------------------------------------------
# BuiltContext (§30) — le contexte métier assemblé
# ------------------------------------------------------------------


class SubjectContextInfo(BaseModel):
    """Config matière exposée au contexte (depuis le Registry)."""

    id: str
    name: str
    domain: str
    description: str = ""
    teaching_style: list[str] = Field(default_factory=list)
    pedagogical_guidelines: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)


class UserContextInfo(BaseModel):
    """Contexte utilisateur sélectionné (mémoire + profil)."""

    text: str = ""
    facts_count: int = 0


class ThreadContextInfo(BaseModel):
    """Contexte thread léger (métadonnées — PAS l'historique, §32)."""

    thread_id: str = ""
    message_count: int | None = None
    text: str = ""


class ContextStats(BaseModel):
    """Budget contexte (§41) — volumétrie approximative."""

    memories_used: int = 0
    knowledge_items: int = 0
    user_context_chars: int = 0
    context_size: int = 0


class BuiltContext(BaseModel):
    """Contexte métier complet assemblé par le Context Builder.

    C'est l'objet structuré unique transmis au Prompt Builder —
    plus de dictionnaire non documenté (§11).
    """

    routing: RoutingResult = Field(default_factory=RoutingResult)
    subject: SubjectContextInfo | None = None
    knowledge: KnowledgeSearchResult = Field(
        default_factory=KnowledgeSearchResult
    )
    tools: ResolvedTools = Field(default_factory=ResolvedTools)
    user: UserContextInfo = Field(
        default_factory=UserContextInfo
    )
    thread: ThreadContextInfo = Field(
        default_factory=ThreadContextInfo
    )
    learning: dict | None = Field(
        default=None,
        description="Réservé Learning Profile (V6+) — toujours null",
    )
    relevant_memories: list[dict] = Field(default_factory=list)
    stats: ContextStats = Field(default_factory=ContextStats)


# Compatibilité d'import pour les modules qui référencent
# RouterResult (ancien nom dataclass du router V4).
__all__ = [
    "AgentContext",
    "RoutingResult",
    "KnowledgeResult",
    "KnowledgeSearchResult",
    "ResolvedTools",
    "ContextPriority",
    "SubjectContextInfo",
    "UserContextInfo",
    "ThreadContextInfo",
    "ContextStats",
    "BuiltContext",
]
