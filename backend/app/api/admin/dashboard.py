"""Admin Dashboard API - Métriques globales et KPIs."""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Any
from datetime import datetime, timedelta

from app.config import CHECKPOINTS_DB_PATH
from app.infrastructure.database.connections import get_conn
from app.auth.resolver import require_admin as get_current_admin_user
# from app.services.models.user import User
# from app.services.models.thread import Thread
# from app.services.models.activity import Activity
# from app.services.models.learning_profile import LearningProfile

router = APIRouter(prefix="/dashboard", tags=["admin-dashboard"])


# États terminaux d'une activité pédagogique ( cf summarize_activity ).
_ACTIVITY_DONE_STATES = frozenset(
    {"understood", "partial", "failed", "completed"}
)


def _activity_stats() -> dict[str, Any]:
    """Compte les activités pédagogiques réelles dans les checkpoints.

    Les activités ne sont PAS en table dédiée : elles vivent dans le
    channel `activity_log` du state LangGraph. On ne lit que le dernier
    checkpoint de chaque thread ( instantané courant ), pas l'historique
    complet — sinon on recompterait N fois la même activité.
    """
    import sqlite3

    try:
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    except ImportError:  # langgraph non installé — zéros honnêtes
        return {"total": 0, "completed": 0, "completion_rate": 0.0}

    stats = {"total": 0, "completed": 0, "completion_rate": 0.0}
    try:
        conn = sqlite3.connect(CHECKPOINTS_DB_PATH)
        try:
            rows = conn.execute(
                """
                SELECT c.type, c.checkpoint
                FROM checkpoints c
                INNER JOIN (
                    SELECT thread_id, MAX(checkpoint_id) AS cid
                    FROM checkpoints GROUP BY thread_id
                ) m ON c.thread_id = m.thread_id AND c.checkpoint_id = m.cid
                """,
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        return stats

    serde = JsonPlusSerializer()
    total = 0
    done = 0
    for type_tag, blob in rows:
        try:
            values = serde.loads_typed((type_tag, blob)).get("channel_values", {})
        except Exception:
            continue
        for entry in values.get("activity_log") or []:
            if not isinstance(entry, dict):
                continue
            total += 1
            if entry.get("status") in _ACTIVITY_DONE_STATES:
                done += 1

    stats["total"] = total
    stats["completed"] = done
    stats["completion_rate"] = round(done / total, 2) if total else 0.0
    return stats


def _learning_profile_count() -> int:
    """Nombre de profils d'apprentissage réels ( LangGraph Store )."""
    try:
        from app.services.memory.memory import get_store
        store = get_store()
        return len(list(store.list_namespaces(prefix=("users", "learning"))))
    except Exception:
        return 0


@router.get("/metrics")
async def get_dashboard_metrics(
    current_user: dict = Depends(get_current_admin_user)
):
    """Récupère les métriques principales du dashboard."""

    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    # Métriques utilisateurs
    conn = get_conn()
    total_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0] or 0
    # Active users 24h based on distinct user_id in threads created >= last_24h
    active_users_24h = conn.execute(
        "SELECT COUNT(DISTINCT user_id) FROM threads WHERE created_at >= ?",
        (last_24h.isoformat(),)
    ).fetchone()[0] or 0
    active_users_7d = conn.execute(
        "SELECT COUNT(DISTINCT user_id) FROM threads WHERE created_at >= ?",
        (last_7d.isoformat(),)
    ).fetchone()[0] or 0

    # Métriques threads
    total_threads = conn.execute('SELECT COUNT(*) FROM threads').fetchone()[0] or 0
    active_threads_24h = conn.execute(
        "SELECT COUNT(*) FROM threads WHERE created_at >= ?",
        (last_24h.isoformat(),)
    ).fetchone()[0] or 0

    # Activités : réelles, lues dans le state des checkpoints
    activities = _activity_stats()

    # Profils d'apprentissage : réels, via le Store
    total_profiles = _learning_profile_count()

    return {
        "users": {
            "total": total_users,
            "active_24h": active_users_24h,
            "active_7d": active_users_7d,
        },
        "threads": {
            "total": total_threads,
            "active_24h": active_threads_24h
        },
        "activities": {
            "total": activities["total"],
            "completed": activities["completed"],
            "completion_rate": activities["completion_rate"]
        },
        "learning": {
            "profiles": total_profiles
        },
        "timestamp": now.isoformat()
    }

@router.get("/activity-stats")
async def get_activity_stats(
    days: int = Query(default=7, ge=1, le=365),
    current_user: dict = Depends(get_current_admin_user)
):
    """Statistiques d'activité sur les X derniers jours."""
    
    # Compute the start date based on the days parameter
    start_date = datetime.utcnow() - timedelta(days=days)
    
    conn = get_conn()
    stats = conn.execute(
        """
        SELECT date(created_at) as date,
               COUNT(*) as thread_count,
               COUNT(DISTINCT user_id) as user_count
        FROM threads
        WHERE created_at >= ?
        GROUP BY date(created_at)
        """,
        (start_date.isoformat(),)
    ).fetchall()
    
    return {
        "daily_stats": [
            {"date": row["date"], "threads": row["thread_count"], "users": row["user_count"]}
            for row in stats
        ],
        "period_days": days,
    }
