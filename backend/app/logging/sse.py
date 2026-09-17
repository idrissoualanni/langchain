# SSE — Server-Sent Events pour les événements agent temps réel
#
# Mission Identité (§22) : ce bus diffuse TOUS les événements (
# messages d'utilisateurs inclus ) → réservé ADMIN. Le token est
# vérifié via le header Authorization ( fetch-based ) OU le query
# `auth` ( EventSource natif ne peut pas poser de headers ). Dans
# les DEUX cas le token est une PREUVE vérifiée par le même
# CurrentUserResolver ( signature/exp/sub réels en mode clerk ) —
# jamais une identité déclarée.
import asyncio
import json

from fastapi import HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app.auth.resolver import _resolve_from_token
from app.logging.events import event_bus, get_recent_events


async def sse_events(request: Request):
    """Endpoint GET /api/events — flux SSE — ADMIN uniquement.

    Auth : Authorization: Bearer <token> (header) OU ?auth=<token>
    ( EventSource ). 401 sans preuve , 403 si non-admin.
    Backfill des 100 derniers events à la connexion, puis stream
    live. Ping toutes les 15 s.
    """
    # 1. Header Authorization ( client fetch )
    header = request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        current = _resolve_from_token(header[7:].strip())
        if not current.is_admin:
            raise HTTPException(403, "Réservé aux administrateurs")
    else:
        # 2. Query auth ( EventSource ) — preuve , pas identité
        token = request.query_params.get("auth", "")
        if not token:
            raise HTTPException(
                401, "Authentification requise (admin)"
            )
        try:
            current = _resolve_from_token(token)
        except HTTPException:
            raise HTTPException(401, "Token invalide")
        if not current.is_admin:
            raise HTTPException(403, "Réservé aux administrateurs")

    queue: asyncio.Queue[dict] = asyncio.Queue()

    async def on_event(event: dict) -> None:
        await queue.put(event)

    sub_id = await event_bus.subscribe(on_event)

    async def gen():
        try:
            # Backfill : les nouveaux clients voient l'activité récente
            for event in get_recent_events(100):
                yield {
                    "event": "agent-event",
                    "data": json.dumps(event, ensure_ascii=False),
                }

            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(
                        queue.get(), timeout=15
                    )
                    yield {
                        "event": "agent-event",
                        "data": json.dumps(item, ensure_ascii=False),
                    }
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            await event_bus.unsubscribe(sub_id)

    return EventSourceResponse(gen())
