# Routes Admin Monitoring — interrogation de agent_events ( Neon ).
#
# La table agent_events persiste TOUS les événements log_event (
# routage, retrieval, fallback, décisions learning, tools, erreurs,
# LiveKit, knowledge… ) : l'admin dispose de l'historique complet des
# actions de l'agent, survive aux redéploiements ( contrairement au
# buffer mémoire event_bus et au fichier agent.log local ).
#
# GET /api/admin/monitoring/events  → derniers événements ( filtres )
# GET /api/admin/monitoring/summary → vue 24 h ( niveaux, top events,
#                                     erreurs, users actifs, volume/h )
# GET /api/admin/monitoring/stats   → état du pipeline d'écriture
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import create_engine, text

from app.auth.resolver import CurrentUser, require_admin
from app.logging.events import get_recent_events
from app.logging import events as _events_mod

router = APIRouter(prefix="/api/admin/monitoring", tags=["admin-monitoring"])

_LEVELS = {"INFO", "WARNING", "ERROR", "DEBUG", "CRITICAL"}


def _engine():
    from app.infrastructure.database.persistence import _postgres_url

    return create_engine(_postgres_url(), pool_pre_ping=True)


@router.get("/events")
def admin_monitoring_events(
    limit: int = Query(default=200, ge=1, le=1000),
    level: str | None = None,
    event: str | None = None,
    user_id: str | None = None,
    thread_id: str | None = None,
    q: str | None = None,
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """Derniers événements persistés — filtres simples, plus récents
    d'abord. `q` cherche dans message/event ( ILIKE )."""
    if level and level.upper() not in _LEVELS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Niveau inconnu : {level}",
        )

    clauses: list[str] = []
    params: dict[str, object] = {"lim": limit}
    if level:
        clauses.append("level = :level")
        params["level"] = level.upper()
    if event:
        clauses.append("event ILIKE :event")
        params["event"] = f"{event}%"
    if user_id:
        clauses.append("user_id = :uid")
        params["uid"] = user_id
    if thread_id:
        clauses.append("thread_id = :tid")
        params["tid"] = thread_id
    if q:
        clauses.append("(message ILIKE :q OR event ILIKE :q)")
        params["q"] = f"%{q}%"

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = (
        "SELECT id, ts, level, event, user_id, thread_id, tool_name, "
        "message, extra FROM agent_events "
        f"{where} ORDER BY ts DESC, id DESC LIMIT :lim"
    )
    try:
        with _engine().connect() as conn:
            rows = conn.execute(text(sql), params).mappings().fetchall()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"agent_events injoignable : {exc}",
        )
    return {
        "events": [
            {
                "id": r["id"],
                "ts": r["ts"].isoformat() if r["ts"] else None,
                "level": r["level"],
                "event": r["event"],
                "user_id": r["user_id"],
                "thread_id": r["thread_id"],
                "tool_name": r["tool_name"],
                "message": r["message"],
                "extra": r["extra"],
            }
            for r in rows
        ],
        "count": len(rows),
    }


@router.get("/summary")
def admin_monitoring_summary(
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """Vue 24 h : volume par niveau, top événements, erreurs, users
    actifs, événements par heure — les chiffres du dashboard."""
    try:
        with _engine().connect() as conn:
            by_level = conn.execute(
                text(
                    "SELECT level, COUNT(*) FROM agent_events "
                    "WHERE ts > now() - interval '24 hours' "
                    "GROUP BY level"
                )
            ).fetchall()
            top_events = conn.execute(
                text(
                    "SELECT event, COUNT(*) AS n FROM agent_events "
                    "WHERE ts > now() - interval '24 hours' "
                    "GROUP BY event ORDER BY n DESC LIMIT 12"
                )
            ).fetchall()
            recent_errors = conn.execute(
                text(
                    "SELECT ts, event, message, thread_id FROM agent_events "
                    "WHERE level IN ('ERROR','CRITICAL') "
                    "  AND ts > now() - interval '24 hours' "
                    "ORDER BY ts DESC LIMIT 20"
                )
            ).fetchall()
            active_users = conn.execute(
                text(
                    "SELECT COUNT(DISTINCT user_id) FROM agent_events "
                    "WHERE user_id <> '' "
                    "  AND ts > now() - interval '24 hours'"
                )
            ).scalar_one()
            per_hour = conn.execute(
                text(
                    "SELECT date_trunc('hour', ts) AS h, COUNT(*) "
                    "FROM agent_events "
                    "WHERE ts > now() - interval '24 hours' "
                    "GROUP BY 1 ORDER BY 1"
                )
            ).fetchall()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"agent_events injoignable : {exc}",
        )
    return {
        "window": "24h",
        "by_level": {r[0]: int(r[1]) for r in by_level},
        "top_events": [
            {"event": r[0], "count": int(r[1])} for r in top_events
        ],
        "recent_errors": [
            {
                "ts": r[0].isoformat() if r[0] else None,
                "event": r[1],
                "message": r[2],
                "thread_id": r[3],
            }
            for r in recent_errors
        ],
        "active_users": int(active_users or 0),
        "per_hour": [
            {"hour": r[0].isoformat(), "count": int(r[1])}
            for r in per_hour
        ],
    }


@router.get("/stats")
def admin_monitoring_stats(
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    """Santé du pipeline de persistance : file, drops, bus mémoire."""
    return {
        "queue_size": _events_mod._event_queue.qsize(),
        "queue_maxsize": _events_mod._event_queue.maxsize,
        "dropped_total": _events_mod._events_dropped,
        "writer_started": _events_mod._writer_started,
        "bus_history": len(get_recent_events(500)),
    }


__all__ = ["router"]
