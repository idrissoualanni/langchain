# Façade du sous-package database (refactor — couche infrastructure).
#
# Ré-exporte l'API publique de persistance SQLite : connexions/migrations
# (connections), CRUD threads (threads) et CRUD utilisateurs (users).
# Les sous-modules restent importables directement
# (ex : app.infrastructure.database.users).
from app.infrastructure.database.connections import (
    MIGRATIONS,
    SCHEMA_STATEMENTS,
    UNIQUE_INDEX,
    get_conn,
    init_db,
)
from app.infrastructure.database.threads import (
    create_thread,
    delete_thread,
    get_thread,
    list_threads,
    rename_thread,
    thread_belongs_to_user,
)
from app.infrastructure.database.users import (
    create_user,
    get_user,
    get_user_by_clerk_id,
    list_users,
)

__all__ = [
    "MIGRATIONS",
    "SCHEMA_STATEMENTS",
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
