# Activity Continuation (Phase 2) — §16.
#
# RÈGLE §16 : si une activité est ACTIVE, on la CONTINUE — on ne crée
# JAMAIS une nouvelle activité parce que l'utilisateur répond à
# l'activité courante. La continuation est pure (déterministe) :
#
#   state → a-t-on une activité continuable ? → oui → répondre au
#   workflow_router que le workflow est "activity".
#
# Le workflow_router (graph/nodes/workflow_router.py) délègue la
# décision à decide_workflow qui détecte déjà les statuts continuables
# (V5.2) — ce module centralise la LOGIQUE de continuation pour être
# réutilisée par le node activity (Phase 2+) et par les tests.
from __future__ import annotations

from typing import Any

from app.schemas.activity import (
    ACTIVITY_IDLE,
    CONTINUABLE_STATUSES,
    TERMINAL_STATUSES,
)


def is_active_activity(activity: dict | None) -> bool:
    """Une activité demandant une réponse / une évaluation est-elle
    en cours (§16) ?

    Statut V5.2 vérifié (source de vérité state) :
      waiting_for_answer, evaluating, giving_hint, waiting_for_retry,
      checking_understanding
    → continuable. idle / completed / abandoned → NON.
    """
    if not activity or not isinstance(activity, dict):
        return False
    status = activity.get("status", ACTIVITY_IDLE)
    return status in CONTINUABLE_STATUSES


def is_terminal_activity(activity: dict | None) -> bool:
    """Activité terminée (completed/abandoned) — plus de continuation."""
    if not activity or not isinstance(activity, dict):
        return False
    return activity.get("status") in TERMINAL_STATUSES


def continuation_target(activity: dict | None) -> str:
    """Workflow cible pour une réponse entrante (§16).

    Retourne "activity" si l'activité courante doit être poursuivie,
    sinon "main" (nouvel échange de chat — pas de continuation).
    """
    if is_active_activity(activity):
        return "activity"
    return "main"


def active_from_state(values: dict | None) -> dict:
    """Activité active extraite d'un state LangGraph (dict state).

    values : snapshot.values du checkpoint (CustomAgentState).
    """
    if not values:
        return {}
    activity = values.get("learning_activity")
    if not isinstance(activity, dict):
        return {}
    return activity if is_active_activity(activity) else {}


def next_step_hint(activity: dict | None) -> dict:
    """Décision de next action DÉTERMINISTE pour la continuation (§16).

    Ne remplace pas l'évaluation (Evaluation Engine, §18-§20) : elle
    décide simplement de la PROCHAINE ÉTAPE selon le statut :
      waiting_for_answer      → évaluer (evaluate)
      giving_hint             → donner l'indice progressif (hint)
      waiting_for_retry       → réévaluer la nouvelle tentative
      checking_understanding  → vérifier la compréhension
      evaluating              → finaliser l'évaluation en cours
    Retourne un dict {kind, detail} — PAS un statut fabriqué.
    """
    if not is_active_activity(activity):
        return {"kind": "none", "detail": "no active activity"}
    status = activity.get("status", ACTIVITY_IDLE)
    mapping: dict[str, dict] = {
        "waiting_for_answer": {
            "kind": "evaluate",
            "detail": "answer expected — evaluate the user's response",
        },
        "evaluating": {
            "kind": "finalize",
            "detail": "evaluation in progress — finish scoring",
        },
        "giving_hint": {
            "kind": "hint",
            "detail": "hint in progress — provide next progressive hint",
        },
        "waiting_for_retry": {
            "kind": "retry",
            "detail": "retry expected — re-evaluate new attempt",
        },
        "checking_understanding": {
            "kind": "understand",
            "detail": "check real understanding before proceeding",
        },
    }
    step = mapping.get(status, {"kind": "continue", "detail": status})
    return {
        "kind": step["kind"],
        "detail": step["detail"],
        "status": status,
    }


__all__ = [
    "is_active_activity",
    "is_terminal_activity",
    "continuation_target",
    "active_from_state",
    "next_step_hint",
]