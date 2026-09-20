# CRUD Threads — UUID backend, liés à un user
import datetime as dt
import uuid

from app.logging.events import log_event
from app.db.connections import get_conn


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def create_thread(user_id: str, name: str) -> dict | None:
    """Crée un thread pour un utilisateur. None si le user n'existe pas."""
    # Vérifie l'existence du user (FK ne suffit pas pour un message propre)
    from app.db.users import get_user

    if get_user(user_id) is None:
        return None

    thread_id = str(uuid.uuid4())
    created_at = _now_iso()

    conn = get_conn()
    conn.execute(
        "INSERT INTO threads (thread_id, user_id, name, created_at) VALUES (?, ?, ?, ?)",
        (thread_id, user_id, name, created_at),
    )
    conn.commit()

    log_event(
        "THREAD_CREATE",
        message=f"Thread created: {name}",
        user_id=user_id,
        thread_id=thread_id,
    )

    return {
        "thread_id": thread_id,
        "user_id": user_id,
        "name": name,
        "created_at": created_at,
    }


def list_threads(user_id: str) -> list[dict]:
    """Liste les threads d'un utilisateur (plus récents en premier)."""
    rows = get_conn().execute(
        "SELECT thread_id, user_id, name, created_at FROM threads "
        "WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_thread(thread_id: str) -> dict | None:
    """Retourne un thread (avec user_id) ou None."""
    row = get_conn().execute(
        "SELECT thread_id, user_id, name, created_at FROM threads WHERE thread_id = ?",
        (thread_id,),
    ).fetchone()
    return dict(row) if row else None


def thread_belongs_to_user(thread_id: str, user_id: str) -> bool:
    """Sécurité : vérifie qu'un thread appartient bien à un utilisateur."""
    row = get_conn().execute(
        "SELECT 1 FROM threads WHERE thread_id = ? AND user_id = ?",
        (thread_id, user_id),
    ).fetchone()
    return row is not None


def rename_thread(thread_id: str, name: str) -> dict | None:
    """Renomme un thread. None si le thread n'existe pas.

    Mission Assistant UI (priorité 6) : renommage persistant côté
    backend — le ThreadList officiel d'assistant-ui appelle
    PUT /api/threads/{id} via l'adaptateur frontend.
    """
    thread = get_thread(thread_id)
    if thread is None:
        return None

    get_conn().execute(
        "UPDATE threads SET name = ? WHERE thread_id = ?",
        (name, thread_id),
    )
    # commit via get_conn (connexion partagée)
    get_conn().commit()

    log_event(
        "THREAD_RENAME",
        message=f"Thread renamed: {name}",
        user_id=thread["user_id"],
        thread_id=thread_id,
    )

    return {**thread, "name": name}


def delete_thread(thread_id: str) -> bool:
    """Supprime un thread. False si le thread n'existe pas.

    Mission Assistant UI : suppression depuis le ThreadList officiel —
    DELETE /api/threads/{id} via l'adaptateur frontend.
    """
    thread = get_thread(thread_id)
    if thread is None:
        return False

    get_conn().execute(
        "DELETE FROM threads WHERE thread_id = ?", (thread_id,)
    )
    get_conn().commit()

    log_event(
        "THREAD_DELETE",
        message=f"Thread deleted: {thread['name']}",
        user_id=thread["user_id"],
        thread_id=thread_id,
    )

    return True
