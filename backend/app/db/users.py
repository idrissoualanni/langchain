# SHIM de compatibilité (refactor — phase migration).
from app.infrastructure.database.users import (
    create_user,
    get_user,
    get_user_by_clerk_id,
    list_users,
)

__all__ = [
    "create_user",
    "get_user",
    "get_user_by_clerk_id",
    "list_users",
]
