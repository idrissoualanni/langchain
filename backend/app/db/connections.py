# SHIM de compatibilité (refactor — phase migration).
from app.infrastructure.database.connections import (
    MIGRATIONS,
    SCHEMA,
    UNIQUE_INDEX,
    get_conn,
    init_db,
)

__all__ = [
    "MIGRATIONS",
    "SCHEMA",
    "UNIQUE_INDEX",
    "get_conn",
    "init_db",
]
