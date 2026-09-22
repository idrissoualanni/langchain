# SHIM de compatibilité (refactor — phase migration).
#
# La persistance SQLite a déménagé vers app/infrastructure/database/.
# SUPPRESSION prévue phase cleanup (§30 mission) après vérification.
from app.infrastructure.database import (
    MIGRATIONS,
    SCHEMA,
    UNIQUE_INDEX,
    create_thread,
    create_user,
    delete_thread,
    get_conn,
    get_thread,
    get_user,
    get_user_by_clerk_id,
    init_db,
    list_threads,
    list_users,
    rename_thread,
    thread_belongs_to_user,
)

__all__ = [
    "MIGRATIONS",
    "SCHEMA",
    "UNIQUE_INDEX",
    "get_conn",
    "init_db",
    "create_thread",
    "delete_thread",
    "get_thread",
    "list_threads",
    "rename_thread",
    "thread_belongs_to_user",
    "create_user",
    "get_user",
    "get_user_by_clerk_id",
    "list_users",
]
