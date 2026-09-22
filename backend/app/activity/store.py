# ActivityStore (Phase 2) — accès standardisé à l'activité du thread
# (§14/§17), par-dessus le state LangGraph V5.2 (source de vérité).
#
# §17 RESUME : une activité doit pouvoir être reprise après
# interruption. On réutilise le CHECKPOINTER unique du graphe parent
# (SqliteSaver, thread_id) — le frontend n'est jamais la source de
# vérité. Ce store est une FACADE de lecture/écriture du channel
# learning_activity du state ; il ne duplique aucun stockage.
from __future__ import annotations

from typing import Any

from app.schemas.activity import (
    ACTIVITY_IDLE,
    CONTINUABLE_STATUSES,
    ActivityContract,
    activity_to_contract,
)
from app.agent.graph import get_agent
from app.logging.events import log_event

# Channel state LangGraph qui porte l'activité du thread (V5.2).
ACTIVITY_CHANNEL = "learning_activity"
_ACTIVITY_LOG_CHANNEL = "activity_log"


def _state_values(user_id: str, thread_id: str) -> dict:
    """Values du checkpoint courant (channel activity incluse)."""
    agent = get_agent()
    try:
        snapshot = agent.get_state(
            {
                "configurable": {
                    "thread_id": thread_id,
                    "user_id": user_id,
                }
            }
        )
    except Exception:
        return {}
    return dict(snapshot.values or {}) if snapshot else {}


def get_activity(
    user_id: str, thread_id: str
) -> dict:
    """Activité brute du thread (dict state) — None/{} si aucune.

    Aucune création ici : si pas d'activité en cours, retour vide.
    """
    values = _state_values(user_id, thread_id)
    activity = values.get(ACTIVITY_CHANNEL)
    if not isinstance(activity, dict):
        return {}
    return activity


def get_activity_contract(
    user_id: str, thread_id: str
) -> ActivityContract:
    """Contrat §15 de l'activité du thread (vue standardisée)."""
    return activity_to_contract(
        get_activity(user_id, thread_id),
        thread_id=thread_id,
        user_id=user_id,
    )


def has_continuable_activity(user_id: str, thread_id: str) -> bool:
    """Y a-t-il une activité EN COURS (§16 continuation) ?

    True seulement si le statut réel du state indique qu'une réponse
    est attendue / une évaluation en cours. Une activité idle ou
    completed ne déclenche JAMAIS la continuation (on ne crée pas de
    nouvelle activité par sur-réaction).
    """
    activity = get_activity(user_id, thread_id)
    if not activity:
        return False
    return activity.get("status") in CONTINUABLE_STATUSES


def summary(
    user_id: str, thread_id: str
) -> dict:
    """Vue API compacte (résumé V5.2 existant, non dupliqué)."""
    from app.schemas.activity import summarize_activity

    activity = get_activity(user_id, thread_id)
    # Résumé API pensé pour le state → on le complète avec le
    # lifecycle produit (§14) pour l'observabilité.
    summary_data = summarize_activity(activity)
    contract = activity_to_contract(
        activity, thread_id=thread_id, user_id=user_id
    )
    summary_data["lifecycle"] = contract.lifecycle
    return summary_data


def save_activity(
    user_id: str,
    thread_id: str,
    activity: dict,
) -> bool:
    """Persiste l'activité du thread via le checkpointer unique.

    Écrit le channel learning_activity du checkpoint courant SANS
    passer par l'invocation (update_state — node interstitiel, aucun
    run LLM). Garde-fous : jamais d'état idle écrasé par du vide.

    Retourne True si le checkpoint a été mis à jour.
    """
    agent = get_agent()
    config = {
        "configurable": {"thread_id": thread_id, "user_id": user_id}
    }
    try:
        agent.update_state(
            config,
            {ACTIVITY_CHANNEL: activity},
            # node interstitiel : valeurs non-réduites, comme un tool.
            as_node="__activity_store__",
        )
        log_event(
            "ACTIVITY_STORE_SAVE",
            message=(
                f"Activity saved | {activity.get('activity_type', '')} "
                f"| status={activity.get('status', ACTIVITY_IDLE)}"
            ),
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "activity_id": activity.get("activity_id", ""),
                "status": activity.get("status", ACTIVITY_IDLE),
            },
        )
        return True
    except Exception as exc:
        log_event(
            "ACTIVITY_STORE_SAVE",
            level="WARNING",
            message=f"Activity save failed (non-bloquant) : {exc}",
            user_id=user_id,
            thread_id=thread_id,
        )
        return False


def clear_activity(user_id: str, thread_id: str) -> bool:
    """Termine la session d'activité du thread (status → idle).

    Utilisé par les nodes de continuation après un feedback final
    (jamais une nouvelle activité : on revient à l'état neuf).
    """
    return save_activity(
        user_id, thread_id, {"status": ACTIVITY_IDLE, "activity_id": ""}
    )


def activity_log(user_id: str, thread_id: str) -> list[dict]:
    """Journal d'activité du thread (dernier 50, ordre chronologique)."""
    values = _state_values(user_id, thread_id)
    log = values.get(_ACTIVITY_LOG_CHANNEL)
    if not isinstance(log, list):
        return []
    return list(log[-50:])


__all__ = [
    "ACTIVITY_CHANNEL",
    "get_activity",
    "get_activity_contract",
    "has_continuable_activity",
    "summary",
    "save_activity",
    "clear_activity",
    "activity_log",
]