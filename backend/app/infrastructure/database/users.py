# CRUD Users — UUID générés côté backend
# Requêtes portables SQLite/PostgreSQL : text() + paramètres nommés
# (:name), jamais « ? » (voir connections.AppConn).
import datetime as dt
import uuid

from app.logging.events import log_event
from app.infrastructure.database.connections import get_conn

_SELECT_USER = (
    "SELECT user_id, name, created_at, clerk_user_id, role "
    "FROM users "
)


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def create_user(
    name: str, clerk_user_id: str | None = None, role: str = "user"
) -> dict:
    """Crée un utilisateur : UUID backend, retourne le user complet.

    Mission Identité : clerk_user_id optionnel (provisioning au
    premier login Clerk) ; role user/admin ('user' par défaut).
    """
    user_id = str(uuid.uuid4())
    created_at = _now_iso()
    conn = get_conn()
    conn.execute(
        "INSERT INTO users (user_id, name, created_at, clerk_user_id, role) "
        "VALUES (:user_id, :name, :created_at, :clerk_user_id, :role)",
        {
            "user_id": user_id,
            "name": name,
            "created_at": created_at,
            "clerk_user_id": clerk_user_id,
            "role": role,
        },
    )
    conn.commit()

    log_event(
        "USER_CREATE",
        message=f"User created: {name}",
        user_id=user_id,
    )

    return {
        "user_id": user_id,
        "name": name,
        "created_at": created_at,
        "clerk_user_id": clerk_user_id,
        "role": role,
    }


def list_users() -> list[dict]:
    """Liste tous les utilisateurs (plus récents en premier)."""
    rows = get_conn().execute(
        _SELECT_USER + "ORDER BY created_at DESC"
    ).fetchall()
    return [dict(row) for row in rows]


def get_user(user_id: str) -> dict | None:
    """Retourne un utilisateur ou None."""
    row = get_conn().execute(
        _SELECT_USER + "WHERE user_id = :user_id",
        {"user_id": user_id},
    ).fetchone()
    return dict(row) if row else None


def get_user_by_clerk_id(clerk_user_id: str) -> dict | None:
    """Mission Identité — lookup par identité externe Clerk.

    Retrouve TOUJOURS le même user interne à la reconnexion ( la
    clé clerk_user_id est UNIQUE en base ).
    """
    row = get_conn().execute(
        _SELECT_USER + "WHERE clerk_user_id = :clerk_user_id",
        {"clerk_user_id": clerk_user_id},
    ).fetchone()
    return dict(row) if row else None