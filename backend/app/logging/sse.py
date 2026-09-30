# SSE — Server-Sent Events pour les événements agent temps réel
#
# Mission Identité (§22) : ce bus diffuse TOUS les événements (
# messages d'utilisateurs inclus ) → réservé ADMIN. Le token est
# vérifié via le header Authorization UNIQUEMENT — le fallback
# `?auth=` a été supprimé ( ES-5 ) : le jeton ne doit pas atterrir
# dans les journaux d'accès. Le token est une PREUVE vérifiée par
# le CurrentUserResolver ( signature/exp/sub réels en mode neon ) —
# jamais une identité déclarée.
import asyncio
import json

from fastapi import HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app.auth.resolver import _resolve_from_token
from app.logging.events import event_bus, get_recent_events


async def sse_events(request: Request):
    """Endpoint GET /api/events — flux SSE — ADMIN uniquement.

    Auth : Authorization: Bearer <token> UNIQUEMENT. 401 sans preuve,
    403 si non-admin. Backfill des 100 derniers events à la connexion,
    puis stream live. Ping toutes les 15 s.
    """
    # 1. Auth — header Authorization Bearer UNIQUEMENT.
    #
    # POURQUOI plus de fallback `?auth=<token>` (ES-5) : ce paramètre
    # était une concession à EventSource natif, incapable de poser des
    # headers. Le jeton finissait alors dans la query string, donc dans
    # les journaux d'accès Render, les journaux de proxy et l'historique
    # du navigateur — une exposition inutile. Le client frontend a migré
    # sur fetch + ReadableStream (apiFetchRaw) qui pose le header : le
    # chemin query est supprimé, le jeton ne transite plus que par header.
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        raise HTTPException(401, "Authentification requise (admin)")
    current = _resolve_from_token(header[7:].strip())
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
