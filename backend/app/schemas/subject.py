# Subject Schemas — configuration des matières ( SubjectConfig ).
#
# Le registry charge ces configs depuis Neon ( subject_definitions ) :
# le YAML est validé par SubjectDefinitionIn ( Pydantic, spec « validé
# par un schéma Pydantic » ) puis normalisé en SubjectConfig ( dataclass
# interne consommée par le router / les tools ).
#
# Deux champs de GOUVERNANCE :
#   - status : cycle de validation admin ( cf. SubjectStatus ) ; un
#     sujet dont status <> "validated" n'est JAMAIS servi à l'agent
#     ( gating au niveau du registry ).
#   - author : auteur de la définition ( métadonnée ).
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import valid_uuid

# Cycle de vie d'une matière — le défaut est fail-closed ( "draft" ).
SubjectStatus = Literal["draft", "review", "validated", "archived"]
SUBJECT_STATUSES: tuple[str, ...] = ("draft", "review", "validated", "archived")


@dataclass
class SubjectConfig:
    """Configuration d'UNE matière. Le moteur ne connaît que ce schéma."""
    id: str
    name: str
    domain: str                      # ex: informatique, sciences
    description: str = ""
    teaching_style: list[str] = field(default_factory=list)
    pedagogical_guidelines: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    tools: dict = field(default_factory=dict)        # {"common": [...], "specialized": [...]}
    knowledge: dict = field(default_factory=dict)    # {"sources": [...]}
    topics: list[str] = field(default_factory=list)   # topics connus (routing)
    aliases: list[str] = field(default_factory=list)  # déclencheurs router (normalisés)
    model: dict = field(default_factory=dict)         # {"provider", "name"} — réservé
    # V7.1 : description sémantique PAR TOPIC — voie déclarative
    # des paraphrases (mission §8) : {topic: [termes FR/EN...]}
    semantic_terms: dict = field(default_factory=dict)
    # Gouvernance — validation admin ( fail-closed ) + auteur.
    status: str = "draft"
    author: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "SubjectConfig":
        return cls(
            id=data["id"],
            name=data["name"],
            domain=data.get("domain", ""),
            description=data.get("description", ""),
            teaching_style=data.get("teaching_style", []),
            pedagogical_guidelines=data.get("pedagogical_guidelines", []),
            capabilities=data.get("capabilities", []),
            tools=data.get("tools", {}),
            knowledge=data.get("knowledge", {}),
            topics=data.get("topics", []),
            aliases=data.get("aliases", []),
            model=data.get("model", {}),
            semantic_terms=data.get("semantic_terms", {}) or {},
            status=data.get("status", "draft") or "draft",
            author=data.get("author", "") or "",
        )


class SubjectDefinitionIn(BaseModel):
    """Validation Pydantic d'une définition de matière ( import / édition ).

    Reprend les champs de SubjectConfig ( spec « validé par un schéma
    Pydantic » ) en tolérant les clés YAML supplémentaires
    (extra="allow") : le YAML riche de l'auteur n'est pas rejeté, mais
    les champs CONNUS sont typés et le statut est contraint à
    SUBJECT_STATUSES.
    """

    model_config = {"extra": "allow"}

    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    domain: str = ""
    description: str = ""
    teaching_style: list[str] = Field(default_factory=list)
    pedagogical_guidelines: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    tools: dict = Field(default_factory=dict)
    knowledge: dict = Field(default_factory=dict)
    topics: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    model: dict = Field(default_factory=dict)
    semantic_terms: dict = Field(default_factory=dict)
    status: SubjectStatus = "draft"
    author: str = Field(default="", max_length=200)


@dataclass
class TopicConfig:
    """Un topic d'une matière (hiérarchie domain > subject > topic)."""
    id: str
    subject_id: str
    name: str
    description: str = ""


class SubjectOut(BaseModel):
    id: str
    name: str
    domain: str
    description: str
    teaching_style: list[str]
    pedagogical_guidelines: list[str]
    capabilities: list[str]
    topics: list[str]
    knowledge_sources: list[str]
    tools_common: list[str]
    tools_specialized: list[str]
    # Gouvernance ( métadonnées exposées à l'admin ).
    status: str = "draft"
    author: str = ""


class TopicOut(BaseModel):
    id: str
    subject_id: str
    name: str


class ContextPreviewRequest(BaseModel):
    """POST /api/subjects/preview/context — outil dev (§35).

    Expose la sélection interne (router, knowledge, mémoire) :
    réservé au développement/debug, à protéger si exposé.
    """

    user_id: str
    thread_id: str | None = Field(default=None, max_length=64)
    query: str = Field(..., min_length=1, max_length=2000)
    subject: str | None = Field(default=None, max_length=50)

    @field_validator("user_id")
    @classmethod
    def valid_user_id(cls, v: str) -> str:
        return valid_uuid(v, "user_id")

    @field_validator("query")
    @classmethod
    def query_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("La requête ne peut pas être vide")
        return v.strip()


class ContextPreviewResponse(BaseModel):
    router: dict
    subject: dict | None
    knowledge: dict
    web: dict | None = None
    # V6.6/V6.8 : décision de fallback + budget (Inspector/dev)
    fallback: dict | None = None
    budget: dict | None = None  # V6.5 §29 : SearchWebResponse web fallback
    tools: dict
    user: dict
    thread: dict
    learning: dict | None = None  # V6 : LearningContextInfo ou null
    prompt_preview: str
    stats: dict
    # V7 §47 : décision pédagogique du Learning Engine (Inspector/
    # dev uniquement — jamais exposée brute à l'étudiant §48)
    learning_strategy: dict | None = None


__all__ = [
    "SubjectConfig",
    "SubjectDefinitionIn",
    "SubjectStatus",
    "SUBJECT_STATUSES",
    "TopicConfig",
    "SubjectOut",
    "TopicOut",
    "ContextPreviewRequest",
    "ContextPreviewResponse",
]
