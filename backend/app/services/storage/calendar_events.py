# MCP agenda store — événements en base ( table calendar_events ).
#
# Anciennement JSON sous data/mcp/calendar.json — éphémère sur Render,
# perdu à chaque redéploiement. Migration Neon : même contrat de tools
# ( check_availability / create_event / list_events ), persistance
# Postgres.
#
# user_id NULL = legacy global ( événements créés avant l'isolation par
# utilisateur ) — JAMAIS rattachés arbitrairement à un user. Les events
# d'un utilisateur sont strictement les siens.
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.config import DATABASE_URL, USE_POSTGRES
from app.logging.events import log_event


class CalendarError(RuntimeError):
    """Erreur métier agenda ( remontée au serveur MCP )."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(value: str) -> datetime | None:
    """Parse ISO ( tolerant : date seule ou datetime )."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None


def _conn():
    """Connexion courte vers Neon ( subprocess stdio : pas de pool global )."""
    if not (USE_POSTGRES and DATABASE_URL):
        raise CalendarError(
            "MCP agenda requiert DATABASE_URL ( Postgres ) — "
            "aucun stockage disque n'est plus supporté."
        )
    from app.infrastructure.database.persistence import _postgres_url

    from sqlalchemy import create_engine

    engine = create_engine(_postgres_url(), pool_pre_ping=True)
    return engine


def _validate_slot(start: str, end: str) -> tuple[datetime, datetime]:
    """Créneau valide → ( start, end ) normalisés, sinon CalendarError."""
    s = _parse_dt(start)
    e = _parse_dt(end)
    if s is None or e is None or e <= s:
        raise CalendarError("Créneau invalide (dates ISO start<end attendues)")
    return s, e


def _row_to_event(row) -> dict:
    def _iso(v):
        return v.isoformat() if hasattr(v, "isoformat") else str(v)
    return {"id": row[0], "title": row[1], "start": _iso(row[2]), "end": _iso(row[3])}


def _as_iso(dt) -> str:
    """datetime → chaîne ISO ( les colonnes start/end sont TEXT )."""
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


# ------------------------------------------------------------------
# API publique — appelée par les 3 tools du serveur MCP agenda
# ------------------------------------------------------------------


def list_events(user_id: str | None, days: int = 7) -> list[dict]:
    """Événements à venir ( horizon `days`, borné à 90 ). Triés par start."""
    horizon = max(1, min(int(days), 90))
    now = datetime.now()
    engine = _conn()
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, title, start, \"end\" FROM calendar_events "
                    "WHERE ( user_id = :uid OR user_id IS NULL ) "
                    "AND CAST(start AS timestamptz) >= CAST(:now AS timestamptz) "
                    "AND CAST(start AS timestamptz) <= CAST(:horizon AS timestamptz) "
                    "ORDER BY start"
                ),
                {
                    "uid": user_id,
                    "now": _as_iso(now),
                    "horizon": _as_iso(now + timedelta(days=horizon)),
                },
            ).fetchall()
        return [_row_to_event(r) for r in rows]
    finally:
        engine.dispose()


def check_availability(user_id: str | None, start: str, end: str) -> dict:
    """Disponibilité sur [ start, end ] via intersection d'intervalles SQL.

    Plus de scan Python : la base répond directement.
    """
    s, e = _validate_slot(start, end)
    engine = _conn()
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, title, start, \"end\" FROM calendar_events "
                    "WHERE ( user_id = :uid OR user_id IS NULL ) "
                    "AND CAST(start AS timestamptz) < CAST(:end_req AS timestamptz) "
                    "AND CAST(\"end\" AS timestamptz) > CAST(:start_req AS timestamptz) "
                    "ORDER BY start"
                ),
                {"uid": user_id, "end_req": _as_iso(e), "start_req": _as_iso(s)},
            ).fetchall()
        conflicts = [_row_to_event(r) for r in rows]
        return {"available": not conflicts, "conflicts": conflicts}
    finally:
        engine.dispose()


def create_event(
    user_id: str | None, title: str, start: str, end: str
) -> dict:
    """Crée un événement ( refuse créneau invalide ou déjà occupé )."""
    title = (title or "").strip()
    if not title:
        raise CalendarError("Titre requis")
    if len(title) > 200:
        raise CalendarError("Titre trop long ( <= 200 caractères )")
    s, e = _validate_slot(start, end)

    # Refuse si chevauchement ( requête d'intersection ).
    check = check_availability(user_id, start, end)
    if not check["available"]:
        raise CalendarError(
            "Créneau déjà occupé : "
            + ", ".join(
                f"'{c['title']}' ({c['start']})" for c in check["conflicts"]
            )
        )

    event_id = "evt-" + hashlib.sha256(
        f"{user_id}:{title}:{s.isoformat()}:{_now()}".encode()
    ).hexdigest()[:16]
    engine = _conn()
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO calendar_events "
                    "(id, title, start, \"end\", created, user_id) "
                    "VALUES (:id, :title, CAST(:start AS timestamptz), "
                    "        CAST(:end AS timestamptz), :created, :uid)"
                ),
                {
                    "id": event_id, "title": title,
                    "start": _as_iso(s), "end": _as_iso(e),
                    "created": _now(), "uid": user_id,
                },
            )
        event = {
            "id": event_id, "title": title,
            "start": s.isoformat(), "end": e.isoformat(),
            "created": _now(),
        }
        log_event(
            "MCP_EVENT_CREATED",
            message=f"Event créé | user={user_id} | title={title}",
            user_id=user_id or "",
        )
        return event
    finally:
        engine.dispose()


def delete_event(event_id: str, user_id: str | None) -> bool:
    """Supprime un événement ( ownership : le sien ou legacy NULL )."""
    engine = _conn()
    try:
        with engine.begin() as conn:
            res = conn.execute(
                text(
                    "DELETE FROM calendar_events "
                    "WHERE id = :id AND ( user_id = :uid OR user_id IS NULL )"
                ),
                {"id": event_id, "uid": user_id},
            )
        return res.rowcount > 0
    finally:
        engine.dispose()


def list_all(user_id: str | None, limit: int = 100) -> list[dict]:
    """Tous les événements ( utilitaire de test/nettoyage )."""
    engine = _conn()
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, title, start, \"end\" FROM calendar_events "
                    "WHERE ( user_id = :uid OR user_id IS NULL ) "
                    "ORDER BY start LIMIT :limit"
                ),
                {"uid": user_id, "limit": limit},
            ).fetchall()
        # pas de cast ici : listing brut, le tri se fait sur la base
        return [_row_to_event(r) for r in rows]
    finally:
        engine.dispose()


__all__ = [
    "CalendarError",
    "list_events",
    "check_availability",
    "create_event",
    "delete_event",
    "list_all",
]
