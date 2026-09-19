"""Admin Dashboard API - Métriques globales et KPIs."""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, count, distinct

from app.core.database import get_db
from app.core.security import get_current_admin_user
from app.models.user import User
from app.models.thread import Thread
from app.models.activity import Activity
from app.models.learning_profile import LearningProfile

router = APIRouter(prefix="/dashboard", tags=["admin-dashboard"])


@router.get("/metrics")
async def get_dashboard_metrics(
    current_user: dict = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Récupère les métriques principales du dashboard."""
    
    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)
    
    # Métriques utilisateurs
    total_users = db.query(func.count(User.id)).scalar() or 0
    active_users_24h = db.query(func.count(distinct(Thread.user_id))).filter(
        Thread.created_at >= last_24h
    ).scalar() or 0
    
    # Métriques threads
    total_threads = db.query(func.count(Thread.id)).scalar() or 0
    active_threads_24h = db.query(func.count(Thread.id)).filter(
        Thread.created_at >= last_24h
    ).scalar() or 0
    
    # Métriques activités
    total_activities = db.query(func.count(Activity.id)).scalar() or 0
    completed_activities = db.query(func.count(Activity.id)).filter(
        Activity.status == "completed"
    ).scalar() or 0
    completion_rate = (completed_activities / total_activities * 100) if total_activities > 0 else 0
    
    # Métriques apprentissage
    total_profiles = db.query(func.count(LearningProfile.id)).scalar() or 0
    
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
    days: int = 7,
    current_user: dict = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Statistiques d'activité sur les X derniers jours."""
    
    now = datetime.utcnow()
    start_date = now - timedelta(days=days)
    
    stats = db.query(
        func.date(Thread.created_at).label('date'),
        func.count(Thread.id).label('thread_count'),
        func.count(distinct(Thread.user_id)).label('user_count')
    ).filter(
        Thread.created_at >= start_date
    ).group_by(
        func.date(Thread.created_at)
    ).all()
    
    return {
        "daily_stats": [
            {
                "date": str(stat.date),
                "threads": stat.thread_count,
                "users": stat.user_count
            }
            for stat in stats
        ],
        "period_days": days
    }
