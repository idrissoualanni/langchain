"""Admin Dashboard API - Métriques globales et KPIs."""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Any
from datetime import datetime, timedelta

from app.db.connections import get_conn
from app.auth.resolver import require_admin as get_current_admin_user
# from app.models.user import User
# from app.models.thread import Thread
# from app.models.activity import Activity
# from app.models.learning_profile import LearningProfile

router = APIRouter(prefix="/dashboard", tags=["admin-dashboard"])

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
    
    # Métriques threads
    total_threads = conn.execute('SELECT COUNT(*) FROM threads').fetchone()[0] or 0
    active_threads_24h = conn.execute(
        "SELECT COUNT(*) FROM threads WHERE created_at >= ?",
        (last_24h.isoformat(),)
    ).fetchone()[0] or 0
    
    # Metrics activities – not stored in DB, placeholder zeros
    total_activities = 0
    completed_activities = 0
    completion_rate = 0.0
    
    # Métriques apprentissage – learning profiles are file‑backed, not in DB
    total_profiles = 0

    return {
        "users": {
            "total": total_users,
            "active_24h": active_users_24h,
            "active_7d": 0  # À implémenter si nécessaire
        },
        "threads": {
            "total": total_threads,
            "active_24h": active_threads_24h
        },
        "activities": {
            "total": total_activities,
            "completed": completed_activities,
            "completion_rate": round(completion_rate, 2)
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
