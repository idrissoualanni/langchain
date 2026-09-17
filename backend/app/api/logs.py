# Route Logs — GET /api/logs (backfill)
#
# Mission Identité (§22) : les logs techniques complets ( messages
# d'utilisateurs inclus ) sont réservés à l'ADMIN. Un user ne
# peut plus lire les logs d'un autre via cette route.
from fastapi import APIRouter, Depends, Query

from app.api.schemas import HealthResponse  # noqa: F401 (réutilisation types)
from app.auth.resolver import CurrentUser, require_admin
from app.logging.events import read_log_file

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("")
def api_logs(
    limit: int = Query(200, ge=1, le=1000),
    level: str | None = None,
    event: str | None = None,
    thread_id: str | None = None,
    current: CurrentUser = Depends(require_admin),
):
    """Lecture des logs structurés (agent.log, JSON-lines) — ADMIN.

    Filtres optionnels : level (INFO/WARNING/ERROR), event, thread_id.
    Retour : plus anciens d'abord, borné par limit.
    """
    logs = read_log_file(limit=limit)

    if level:
        logs = [
            l
            for l in logs
            if l.get("level", "").upper() == level.upper()
        ]
    if event:
        logs = [
            l
            for l in logs
            if l.get("event", "") == event
        ]
    if thread_id:
        logs = [
            l for l in logs if l.get("thread_id", "") == thread_id
        ]

    return logs
