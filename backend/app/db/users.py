# CRUD Users — UUID générés côté backend
import datetime as dt
import uuid

from app.logging.events import log_event
from app.db.connections import get_conn


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def create_user(name: str) -> dict:
    """Crée un utilisateur : UUID backend, retourne le user complet."""
    user_id = str(uuid.uuid4())
    created_at = _now_iso()
    conn = get_conn()
    conn.execute(
        "INSERT INTO users (user_id, name, created_at) VALUES (?, ?, ?)",
        (user_id, name, created_at),
    )
    conn.commit()

    log_event(
        "USER_CREATE",
        message=f"User created: {name}",
        user_id=user_id,
    )

    return {"user_id": user_id, "name": name, "created_at": created_at}


def list_users() -> list[dict]:
    """Liste tous les utilisateurs (plus récents en premier)."""
    rows = get_conn().execute(
        "SELECT user_id, name, created_at FROM users ORDER BY created_at DESC"
    ).fetchall()
    return [dict(row) for row in rows]


def get_user(user_id: str) -> dict | None:
    """Retourne un utilisateur ou None."""
    row = get_conn().execute(
        "SELECT user_id, name, created_at FROM users WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None
