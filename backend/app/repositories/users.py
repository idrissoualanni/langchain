"""Repository des utilisateurs (façade au-dessus de ``app.infrastructure.database.users``)."""
from __future__ import annotations

from app.infrastructure.database import users as _users_db


def create_user(
    name: str, clerk_user_id: str | None = None, role: str = "user"
) -> dict:
    """Crée un utilisateur et retourne son enregistrement complet."""
    return _users_db.create_user(
        name, clerk_user_id=clerk_user_id, role=role
    )


def list_users() -> list[dict]:
    """Liste tous les utilisateurs (plus récents en premier)."""
    return _users_db.list_users()


def get_user(user_id: str) -> dict | None:
    """Retourne un utilisateur ou None s'il n'existe pas."""
    return _users_db.get_user(user_id)


def get_user_by_clerk_id(clerk_user_id: str) -> dict | None:
    """Retrouve un utilisateur par son identifiant externe Clerk."""
    return _users_db.get_user_by_clerk_id(clerk_user_id)


__all__ = [
    "create_user",
    "list_users",
    "get_user",
    "get_user_by_clerk_id",
]
