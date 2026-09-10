# Schemas Pydantic — validation stricte des entrées API
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


def _valid_uuid(value: str, field_name: str) -> str:
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        raise ValueError(f"{field_name} doit être un UUID valide")
    return value


class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Le nom ne peut pas être vide")
        return v.strip()


class UserOut(BaseModel):
    user_id: str
    name: str
    created_at: str


class ThreadCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Le nom du thread ne peut pas être vide")
        return v.strip()


class ThreadOut(BaseModel):
    thread_id: str
    user_id: str
    name: str
    created_at: str


class ChatRequest(BaseModel):
    user_id: str
    thread_id: str
    message: str = Field(..., min_length=1, max_length=10_000)

    @field_validator("user_id")
    @classmethod
    def valid_user_id(cls, v: str) -> str:
        return _valid_uuid(v, "user_id")

    @field_validator("thread_id")
    @classmethod
    def valid_thread_id(cls, v: str) -> str:
        return _valid_uuid(v, "thread_id")

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Le message ne peut pas être vide")
        return v.strip()


class ChatResponse(BaseModel):
    response: str
    user_id: str
    thread_id: str
    interaction_count: int


class MessageOut(BaseModel):
    type: str
    content: str
    tool_calls: list[dict] | None = None


class StateResponse(BaseModel):
    user_id: str
    thread_id: str
    interaction_count: int
    message_count: int
    messages: list[MessageOut]


class CheckpointOut(BaseModel):
    checkpoint_id: str | None
    created_at: str
    message_count: int
    interaction_count: int
    summary: str


class HealthResponse(BaseModel):
    status: str
    ollama: bool
    langgraph: bool
    sqlite: bool
    model: str


# ------------------------------------------------------------------
# Mémoire longue durée — profil utilisateur
# ------------------------------------------------------------------


class ProfileOut(BaseModel):
    user_id: str
    name: str | None
    description: str | None
    exists: bool


class ProfileUpdate(BaseModel):
    """PUT /api/users/{user_id}/profile — champs autorisés uniquement."""
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("user_id", check_fields=False)
    @classmethod
    def never_user_id(cls, v):
        # user_id vient uniquement du path — jamais du body
        if v is not None:
            raise ValueError("user_id n'est pas modifiable via le body")
        return v

    @field_validator("name", "description")
    @classmethod
    def strip_values(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        return v


# ------------------------------------------------------------------
# MemoryFacts v3 — faits individuels par catégorie
# ------------------------------------------------------------------


class MemoryFactOut(BaseModel):
    id: str
    category: str
    content: str
    source: str
    confidence: float
    created_at: str
    updated_at: str


class MemoryOverviewOut(BaseModel):
    user_id: str
    identity: dict
    facts_by_category: dict[str, list[MemoryFactOut]]
    total_facts: int
    categories: list[str]


class MemoryFactCreate(BaseModel):
    """POST /api/users/{id}/memory — création manuelle d'un fait."""
    category: str = Field(..., max_length=50)
    content: str = Field(..., min_length=1, max_length=2000)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("category")
    @classmethod
    def valid_category(cls, v: str) -> str:
        from app.agent.memory import FACT_CATEGORIES

        if v not in FACT_CATEGORIES:
            raise ValueError(
                f"Catégorie inconnue : {v}. "
                f"Catégories autorisées : {list(FACT_CATEGORIES)}"
            )
        return v

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Le contenu ne peut pas être vide")
        return v.strip()


class MemoryFactUpdate(BaseModel):
    """PUT /api/users/{id}/memory/{fact_id} — update ciblé."""
    content: str | None = Field(
        default=None, min_length=1, max_length=2000
    )
    category: str | None = Field(default=None, max_length=50)

    @field_validator("category")
    @classmethod
    def valid_category(cls, v: str | None) -> str | None:
        if v is None:
            return None
        from app.agent.memory import FACT_CATEGORIES

        if v not in FACT_CATEGORIES:
            raise ValueError(
                f"Catégorie inconnue : {v}. "
                f"Catégories autorisées : {list(FACT_CATEGORIES)}"
            )
        return v

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not v.strip():
            raise ValueError("Le contenu ne peut pas être vide")
        return v.strip()


# ------------------------------------------------------------------
# V4 — Subjects & Context Preview
# ------------------------------------------------------------------


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
        return _valid_uuid(v, "user_id")

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
    tools: dict
    user: dict
    thread: dict
    prompt_preview: str
    stats: dict
