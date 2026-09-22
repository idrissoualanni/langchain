# SHIM de compatibilité (refactor — phase migration).
from app.infrastructure.database.threads import (
    create_thread,
    delete_thread,
    get_thread,
    list_threads,
    rename_thread,
    thread_belongs_to_user,
)

__all__ = [
    "create_thread",
    "delete_thread",
    "get_thread",
    "list_threads",
    "rename_thread",
    "thread_belongs_to_user",
]
