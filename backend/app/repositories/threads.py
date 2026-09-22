"""Repository des threads (façade au-dessus de ``app.infrastructure.database.threads``)."""
from __future__ import annotations

from app.infrastructure.database import threads as _threads_db


def create_thread(user_id: str, name: str) -> dict | None:
    """Crée un thread pour un utilisateur (None si user inconnu)."""
    return _threads_db.create_thread(user_id, name)


def list_threads(user_id: str) -> list[dict]:
    """Liste les threads d'un utilisateur (plus récents en premier)."""
    return _threads_db.list_threads(user_id)


def get_thread(thread_id: str) -> dict | None:
    """Retourne un thread ou None s'il n'existe pas."""
    return _threads_db.get_thread(thread_id)


def thread_belongs_to_user(thread_id: str, user_id: str) -> bool:
    """Vérifie qu'un thread appartient bien à un utilisateur."""
    return _threads_db.thread_belongs_to_user(thread_id, user_id)


def rename_thread(thread_id: str, name: str) -> dict | None:
    """Renomme un thread (None si le thread n'existe pas)."""
    return _threads_db.rename_thread(thread_id, name)


def delete_thread(thread_id: str) -> bool:
    """Supprime un thread (False si le thread n'existe pas)."""
    return _threads_db.delete_thread(thread_id)


__all__ = [
    "create_thread",
    "list_threads",
    "get_thread",
    "thread_belongs_to_user",
    "rename_thread",
    "delete_thread",
]
