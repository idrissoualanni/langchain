# Activity Schemas — TOUT le domaine activité pédagogique.
#
# Fusion refactor (source unique du domaine) :
#   - état thread-local (ex app/agent/activity_state.py) : statuts V5.2,
#     LearningActivityState/QuizState/ActivityLogEntry, helpers ;
#   - contrat produit (ex app/activity/schemas.py) : ActivityContract,
#     lifecycle §14, projection state→contrat ;
#   - vues API Pydantic (ex app/api/schemas.py) : résumé thread, code.
#
# L'activité VIT dans le state LangGraph, persistée par le
# checkpointer natif : aucun stockage manuel parallèle.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import valid_uuid

# ------------------------------------------------------------------
# État thread-local V5.2 (source de vérité du state LangGraph)
# ------------------------------------------------------------------

# Statuts d'une activité (§15)
ACTIVITY_IDLE = "idle"
ACTIVITY_WAITING_ANSWER = "waiting_for_answer"
ACTIVITY_EVALUATING = "evaluating"
ACTIVITY_GIVING_HINT = "giving_hint"
ACTIVITY_WAITING_RETRY = "waiting_for_retry"
ACTIVITY_CHECKING_UNDERSTANDING = "checking_understanding"
ACTIVITY_COMPLETED = "completed"
ACTIVITY_ABANDONED = "abandoned"

ALL_ACTIVITY_STATUSES = [
    ACTIVITY_IDLE,
    ACTIVITY_WAITING_ANSWER,
    ACTIVITY_EVALUATING,
    ACTIVITY_GIVING_HINT,
    ACTIVITY_WAITING_RETRY,
    ACTIVITY_CHECKING_UNDERSTANDING,
    ACTIVITY_COMPLETED,
    ACTIVITY_ABANDONED,
]

# Types d'activité
ACTIVITY_TYPE_EXERCISE = "exercise"
ACTIVITY_TYPE_QUIZ = "quiz"
ACTIVITY_TYPE_UNDERSTANDING_CHECK = "understanding_check"

# Types de réponse attendue (§23)
RESPONSE_TYPE_TEXT = "text"
RESPONSE_TYPE_CODE = "code"
RESPONSE_TYPE_MULTIPLE_CHOICE = "multiple_choice"
RESPONSE_TYPE_SHORT_ANSWER = "short_answer"
RESPONSE_TYPE_TRUE_FALSE = "true_false"

ALL_RESPONSE_TYPES = [
    RESPONSE_TYPE_TEXT,
    RESPONSE_TYPE_CODE,
    RESPONSE_TYPE_MULTIPLE_CHOICE,
    RESPONSE_TYPE_SHORT_ANSWER,
    RESPONSE_TYPE_TRUE_FALSE,
]


class LearningActivityState(TypedDict, total=False):
    """Activité pédagogique EN COURS dans CE thread (§14).

    Thread-local par construction : le state LangGraph est scoppé au
    thread_id du checkpointer. Redémarrage backend → thread repris →
    l'activité est restaurée telle quelle (§16), sans stockage manuel.
    """

    activity_id: str
    activity_type: str  # exercise | quiz | understanding_check
    subject: str
    topic: str
    status: str  # cf. ALL_ACTIVITY_STATUSES
    question: str
    expected_response_type: str  # cf. ALL_RESPONSE_TYPES
    source: str  # ex: informatique/python/functions
    hint_level: int
    attempts: int
    awaiting_answer: bool
    last_evaluation: dict  # dernier retour evaluate_answer
    understanding: dict  # dernier retour assess_understanding
    started_at: str  # ISO timestamp
    question_index: int  # quiz : index de la question courante


class QuizState(LearningActivityState, total=False):
    """Quiz interactif — une question à la fois, jamais un dump (§17-§20).

    Le quiz EST une activité (activity_type=quiz) : plutôt qu'un state
    parallèle, on réutilise le même champ learning_activity avec les
    champs quiz dédiés ci-dessous. Simple, minimal (§18).
    """

    questions: list[dict]  # [{question, expected, terms, source}]
    total_questions: int
    current_index: int
    score: float
    awaiting_answer: bool


class ActivityLogEntry(TypedDict, total=False):
    """Une entrée du journal d'activité thread-local (§42 frontend).

    Né des événements réels ACTIVITY_* émis par les tools — jamais
    fabriquée côté frontend.
    """

    timestamp: str
    event: str  # ACTIVITY_* | QUIZ_* | CODE_*
    status: str
    detail: str
    hint_level: int
    activity_type: str


def new_activity_id(subject: str, topic: str) -> str:
    """Id court et stable d'une activité pour le front/le state."""
    import re
    import time

    slug = re.sub(r"[^a-z0-9]+", "-", f"{subject}-{topic}".lower())
    return f"{slug}-{int(time.time() * 1000)}"


def summarize_activity(activity: dict | None) -> dict:
    """Vue compacte pour l'API/le frontend — sans le contenu complet
    des questions (évite de fuiter les réponses attendues au client).
    """
    if not activity:
        return {
            "status": ACTIVITY_IDLE,
            "activity_type": None,
            "subject": None,
            "topic": None,
        }
    quiz = activity.get("activity_type") == ACTIVITY_TYPE_QUIZ
    return {
        "activity_id": activity.get("activity_id", ""),
        "activity_type": activity.get("activity_type", ""),
        "subject": activity.get("subject", ""),
        "topic": activity.get("topic", ""),
        "status": activity.get("status", ACTIVITY_IDLE),
        "hint_level": activity.get("hint_level", 0),
        "attempts": activity.get("attempts", 0),
        "awaiting_answer": bool(activity.get("awaiting_answer")),
        "expected_response_type": activity.get(
            "expected_response_type", RESPONSE_TYPE_TEXT
        ),
        "question_index": activity.get("question_index", 0),
        "total_questions": (
            activity.get("total_questions", 0) if quiz else 0
        ),
        "current_index": activity.get("current_index", 0) if quiz else 0,
        "score": activity.get("score", 0.0) if quiz else None,
    }


# ------------------------------------------------------------------
# Contrat produit §14/§15 (vue standardisée, pas de second stockage)
# ------------------------------------------------------------------

# Lifecycle §14 (vue produit, mappée sur les statuts V5.2 réels).
# "created → ready → in_progress → waiting_for_answer → evaluating →
# feedback → completed" + états d'erreur (failed/cancelled/expired).
LIFECYCLE_CREATED = "created"
LIFECYCLE_READY = "ready"
LIFECYCLE_IN_PROGRESS = "in_progress"
LIFECYCLE_WAITING_ANSWER = "waiting_for_answer"
LIFECYCLE_EVALUATING = "evaluating"
LIFECYCLE_FEEDBACK = "feedback"
LIFECYCLE_COMPLETED = "completed"
LIFECYCLE_FAILED = "failed"
LIFECYCLE_CANCELLED = "cancelled"
LIFECYCLE_EXPIRED = "expired"

# Statuts V5.2 qui signifient "une réponse est attendue / en cours" —
# la continuation §16 ne crée JAMAIS une nouvelle activité dans ces états.
CONTINUABLE_STATUSES: frozenset[str] = frozenset(
    {
        ACTIVITY_WAITING_ANSWER,
        ACTIVITY_EVALUATING,
        ACTIVITY_GIVING_HINT,
        ACTIVITY_WAITING_RETRY,
        ACTIVITY_CHECKING_UNDERSTANDING,
    }
)

# Statuts terminaux (§14 errors) — aucune continuation possible.
TERMINAL_STATUSES: frozenset[str] = frozenset(
    {
        ACTIVITY_COMPLETED,
        ACTIVITY_ABANDONED,
    }
)

# Types d'activité §14 (le repos implémente ces 3 ; les autres
# arriveront avec leurs subgraphs — Problem/Coding/Video).
ACTIVITY_TYPES = (
    ACTIVITY_TYPE_EXERCISE,
    ACTIVITY_TYPE_QUIZ,
    ACTIVITY_TYPE_UNDERSTANDING_CHECK,
)


def lifecycle_stage(status: str | None) -> str:
    """Mappe un statut V5.2 vers l'étape de lifecycle §14.

    Le lifecycle produit n'introduit PAS une nouvelle machine : il
    est dérivé du statut state réel (source unique de vérité).
    """
    if status is None or status == ACTIVITY_IDLE:
        return LIFECYCLE_CREATED
    if status == ACTIVITY_COMPLETED:
        return LIFECYCLE_COMPLETED
    if status == ACTIVITY_ABANDONED:
        return LIFECYCLE_CANCELLED
    if status == ACTIVITY_CHECKING_UNDERSTANDING:
        return LIFECYCLE_FEEDBACK
    # waiting_for_answer / evaluating / giving_hint / waiting_for_retry
    # sont "en cours d'interaction" (§16) → in_progress sauf khi une
    # réponse est strictement attendue.
    if status in CONTINUABLE_STATUSES:
        return LIFECYCLE_IN_PROGRESS
    return LIFECYCLE_CREATED


@dataclass(slots=True)
class ActivityContract:
    """Contrat d'activité §15 — vue produit alignée sur le state.

    L'activité VIT dans le state LangGraph (LearningActivityState) ;
    ce contrat est la projection standardisée consommée par le
    ActivityStore / API / subgraphs (Phase 2+). zéro duplication de
    stockage : c'est une VUE, pas une seconde source de vérité.
    """

    activity_id: str = ""
    thread_id: str = ""
    user_id: str = ""
    activity_type: str = ""
    subject: str = ""
    topic: str = ""
    status: str = ACTIVITY_IDLE
    created_at: str = ""
    updated_at: str = ""
    payload: dict = field(default_factory=dict)
    attempt_count: int = 0
    current_step: int = 0  # question_index réalisé (quiz)
    result: dict = field(default_factory=dict)  # dernière évaluation

    @property
    def lifecycle(self) -> str:
        return lifecycle_stage(self.status)

    @property
    def continuable(self) -> bool:
        return self.status in CONTINUABLE_STATUSES


def activity_to_contract(
    activity: dict | None,
    thread_id: str = "",
    user_id: str = "",
) -> ActivityContract:
    """Projection state (dict LearningActivityState) → contrat §15.

    Ne garde que les champs du contrat — les internes (question,
    expected answer — les données de l'exercice ne sont
    JAMAIS mises dans le prompt).
    """
    a = activity or {}
    return ActivityContract(
        activity_id=a.get("activity_id", ""),
        thread_id=thread_id or a.get("thread_id", ""),
        user_id=user_id or a.get("user_id", ""),
        activity_type=a.get("activity_type", ""),
        subject=a.get("subject", ""),
        topic=a.get("topic", ""),
        status=a.get("status", ACTIVITY_IDLE),
        created_at=a.get("started_at", ""),
        updated_at=a.get("updated_at", ""),
        payload=_public_payload(a),
        attempt_count=a.get("attempts", 0),
        current_step=a.get("question_index", 0),
        result=dict(a.get("result") or a.get("last_evaluation") or {}),
    )


def _public_payload(activity: dict) -> dict:
    """Payload public §15 (sans fuite des réponses attendues)."""
    payload: dict = {}
    if activity.get("expected_response_type"):
        payload["expected_response_type"] = activity.get(
            "expected_response_type"
        )
    if activity.get("hint_level"):
        payload["hint_level"] = activity.get("hint_level")
    if activity.get("awaiting_answer") is not None:
        payload["awaiting_answer"] = bool(activity.get("awaiting_answer"))
    return payload


def make_result(
    score: float | None,
    verdict: str,
    strengths: list[str],
    weaknesses: list[str],
    feedback: str,
    evidence: list[dict] | None = None,
    confidence: float = 1.0,
) -> dict:
    """Dict résultat d'évaluation (aligné §20, stocké dans activity
    ["result"] / ["last_evaluation"]). Structure STABLE pour l'API."""
    return {
        "score": score,
        "verdict": verdict,
        "strengths": [str(s) for s in strengths],
        "weaknesses": [str(w) for w in weaknesses],
        "feedback": feedback,
        "evidence": list(evidence or []),
        "confidence": confidence,
    }


# ------------------------------------------------------------------
# Vues API Pydantic (ex app/api/schemas.py — contrats /api/threads)
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
        return valid_uuid(v, "user_id")

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


__all__ = [
    "ACTIVITY_ABANDONED",
    "ACTIVITY_CHECKING_UNDERSTANDING",
    "ACTIVITY_COMPLETED",
    "ACTIVITY_EVALUATING",
    "ACTIVITY_GIVING_HINT",
    "ACTIVITY_IDLE",
    "ACTIVITY_WAITING_ANSWER",
    "ACTIVITY_WAITING_RETRY",
    "ACTIVITY_TYPE_EXERCISE",
    "ACTIVITY_TYPE_QUIZ",
    "ACTIVITY_TYPE_UNDERSTANDING_CHECK",
    "ALL_ACTIVITY_STATUSES",
    "ALL_RESPONSE_TYPES",
    "RESPONSE_TYPE_CODE",
    "RESPONSE_TYPE_MULTIPLE_CHOICE",
    "RESPONSE_TYPE_SHORT_ANSWER",
    "RESPONSE_TYPE_TEXT",
    "RESPONSE_TYPE_TRUE_FALSE",
    "LIFECYCLE_CREATED",
    "LIFECYCLE_READY",
    "LIFECYCLE_IN_PROGRESS",
    "LIFECYCLE_WAITING_ANSWER",
    "LIFECYCLE_EVALUATING",
    "LIFECYCLE_FEEDBACK",
    "LIFECYCLE_COMPLETED",
    "LIFECYCLE_FAILED",
    "LIFECYCLE_CANCELLED",
    "LIFECYCLE_EXPIRED",
    "CONTINUABLE_STATUSES",
    "TERMINAL_STATUSES",
    "ACTIVITY_TYPES",
    "LearningActivityState",
    "QuizState",
    "ActivityLogEntry",
    "new_activity_id",
    "summarize_activity",
    "lifecycle_stage",
    "ActivityContract",
    "activity_to_contract",
    "make_result",
    "ActivitySummary",
    "ActivityLogEntryOut",
    "ThreadActivityResponse",
    "CodeRunRequest",
    "CodeRunResponse",
]
