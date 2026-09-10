# Connexions SQLite — app.db (users/threads) avec init schema
import sqlite3
import threading
from pathlib import Path

from app.config import APP_DB_PATH

_local = threading.local()
_init_lock = threading.Lock()
_initialized = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS threads (
    thread_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    name TEXT NOT NULL DEFAULT 'New Thread',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_threads_user ON threads(user_id);
"""


def get_conn() -> sqlite3.Connection:
    """Connexion SQLite par thread (thread-safe pour FastAPI threadpool)."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(APP_DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return conn


def init_db() -> None:
    """Crée le schema users/threads si nécessaire (idempotent)."""
    global _initialized
    with _init_lock:
        if _initialized:
            return
        conn = get_conn()
        conn.executescript(SCHEMA)
        conn.commit()
        _initialized = True
