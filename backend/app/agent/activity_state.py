# Activity State V5.2 — schémas des activités pédagogiques en cours.
#
# PHILOSOPHIE (§14 du brief) : l'activité pédagogique (exercice, quiz,
# vérification de compréhension) appartient au THREAD COURANT — pas à
# la User Memory (cross-thread), pas au Learning Profile (mission de
# l'autre agent). Elle vit dans le State LangGraph, persistée par le
# checkpointer natif : aucun stockage manuel parallèle.
#
# Ces schémas sont des TypedDict purs — les valeurs stockées dans le
# state sont de simples dicts sérialisables (SqliteSaver / JsonPlusSerializer).
from __future__ import annotations

from typing import TypedDict


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
