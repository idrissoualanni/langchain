"""Repository de l'activité du thread (façade de ``activity.store``)."""
from __future__ import annotations

from app.schemas.activity import ActivityContract
from app.services.activity import store as _activity_service


# Canal d'état LangGraph portant l'activité (exposé tel quel).
ACTIVITY_CHANNEL: str = _activity_service.ACTIVITY_CHANNEL


def get_activity(user_id: str, thread_id: str) -> dict:
    """Retourne l'activité brute du thread (vide si aucune)."""
    return _activity_service.get_activity(user_id, thread_id)


def get_activity_contract(
    user_id: str, thread_id: str
) -> ActivityContract:
    """Retourne le contrat standardisé de l'activité du thread."""
    return _activity_service.get_activity_contract(user_id, thread_id)


def has_continuable_activity(user_id: str, thread_id: str) -> bool:
    """Indique si le thread porte une activité à poursuivre."""
    return _activity_service.has_continuable_activity(user_id, thread_id)


def summary(user_id: str, thread_id: str) -> dict:
    """Retourne la vue API compacte de l'activité du thread."""
    return _activity_service.summary(user_id, thread_id)


def save_activity(
    user_id: str, thread_id: str, activity: dict
) -> bool:
    """Persiste l'activité du thread (True si le dépôt a réussi)."""
    return _activity_service.save_activity(user_id, thread_id, activity)


def clear_activity(user_id: str, thread_id: str) -> bool:
    """Termine la session d'activité du thread (retour à l'état neutre)."""
    return _activity_service.clear_activity(user_id, thread_id)


def activity_log(user_id: str, thread_id: str) -> list[dict]:
    """Retourne le journal d'activité du thread (ordre chronologique)."""
    return _activity_service.activity_log(user_id, thread_id)


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
