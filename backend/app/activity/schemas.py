# Activity Schemas (Phase 2) — contrat d'activité standardisé (§15)
# + lifecycle §14, alignés sur la machine d'état V5.2 existante
# (app.agent.activity_state). On STANDARDISE, on ne recrée pas :
# les statuts V5.2 restent la source de vérité du state LangGraph.
"""
Contrat d'activité (§14/§15).

Ré-exporte et étend la machine V5.2 :
  - les CONSTANTES de statut/type viennent de activity_state (source
    unique) ;
  - ActivityContract aligne les champs produit (§15) avec les champs
    state (LearningActivityState) SANS en créer une copie parallèle.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.agent.activity_state import (  # source de vérité (V5.2)
    ACTIVITY_ABANDONED,
    ACTIVITY_CHECKING_UNDERSTANDING,
    ACTIVITY_COMPLETED,
    ACTIVITY_EVALUATING,
    ACTIVITY_GIVING_HINT,
    ACTIVITY_IDLE,
    ACTIVITY_WAITING_ANSWER,
    ACTIVITY_WAITING_RETRY,
    ACTIVITY_TYPE_EXERCISE,
    ACTIVITY_TYPE_QUIZ,
    ACTIVITY_TYPE_UNDERSTANDING_CHECK,
    ALL_ACTIVITY_STATUSES,
    RESPONSE_TYPE_CODE,
    RESPONSE_TYPE_MULTIPLE_CHOICE,
    RESPONSE_TYPE_SHORT_ANSWER,
    RESPONSE_TYPE_TEXT,
    RESPONSE_TYPE_TRUE_FALSE,
)

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
    expected_response_type, source, hint_level, questions quiz)
    restent privés au state (frontière API, cf. summarize_activity).
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
    "lifecycle_stage",
    "ActivityContract",
    "activity_to_contract",
    "make_result",
]