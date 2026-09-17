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
    # Mission Identité — infos session (optionnelles)
    clerk_user_id: str | None = None
    role: str = "user"
    # MODE DEV UNIQUEMENT : token de session simulée pour les
    # suites de régression ("dev:<internal_user_id>"). Jamais
    # renseigné en mode clerk.
    dev_token: str | None = None


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


class ThreadRename(BaseModel):
    """PUT /api/threads/{thread_id} — renommage (assistant-ui)."""
    name: str = Field(..., min_length=1, max_length=150)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Le nom du thread ne peut pas être vide")
        return v.strip()


class ChatRequest(BaseModel):
    # Mission Identité : user_id/thread_id restent au contrat pour
    # la rétrocompatibilité du format, MAIS l'identité vient du
    # Bearer token (get_current_user). Le user_id fourni ici est
    # VÉRIFIÉ contre l'utilisateur courant (403 si usurpation) —
    # il ne définit JAMAIS qui est l'utilisateur.
    user_id: str
    thread_id: str
    message: str = Field(..., min_length=1, max_length=10_000)
    # Mission Assistant UI (ModelSelector) : modèle Ollama optionnel.
    # None/absent → modèle par défaut (MODEL_NAME, env). Aucun autre
    # comportement backend ne dépend de ce champ.
    model: str | None = Field(default=None, max_length=100)

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

    @field_validator("model")
    @classmethod
    def valid_model(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class ChatResponse(BaseModel):
    response: str
    # V6.7 : réponse structurée (contrat AgentResponse) — le
    # texte brut reste pour rétrocompatibilité.
    agent_response: dict | None = None
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
    # V6.8 (audit §62 G.3) : nature du checkpoint — le frontend
    # consomme ce champ structuré au lieu de parser le summary.
    kind: str = "state"


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


# ------------------------------------------------------------------
# V5.2 — Activité pédagogique & pratique du code
# ------------------------------------------------------------------


class ActivitySummary(BaseModel):
    """Vue de l'activité en cours (sans fuiter les réponses)."""
    activity_id: str = ""
    activity_type: str | None = None
    subject: str | None = None
    topic: str | None = None
    status: str = "idle"
    hint_level: int = 0
    attempts: int = 0
    awaiting_answer: bool = False
    expected_response_type: str = ""
    question_index: int = 0
    total_questions: int = 0
    current_index: int = 0
    score: float | None = None


class ActivityLogEntryOut(BaseModel):
    timestamp: str = ""
    event: str = ""
    status: str = ""
    detail: str = ""
    hint_level: int = 0
    activity_type: str = ""


class ThreadActivityResponse(BaseModel):
    thread_id: str
    user_id: str
    activity: ActivitySummary
    activity_log: list[ActivityLogEntryOut]
    interaction_count: int = 0


class CodeRunRequest(BaseModel):
    """POST /api/threads/{id}/run-code — Code Editor backend."""
    user_id: str
    code: str = Field(..., min_length=1, max_length=8000)

    @field_validator("user_id")
    @classmethod
    def valid_user_id(cls, v: str) -> str:
        return _valid_uuid(v, "user_id")

    @field_validator("code")
    @classmethod
    def code_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Le code ne peut pas être vide")
        return v


class CodeRunResponse(BaseModel):
    status: str
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
