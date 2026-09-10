# SSE — Server-Sent Events pour les événements agent temps réel
import asyncio
import json

from fastapi import Request
from sse_starlette.sse import EventSourceResponse

from app.logging.events import event_bus, get_recent_events


async def sse_events(request: Request):
    """Endpoint GET /api/events — flux SSE de tous les événements agent.

    Backfill des 100 derniers events au connexion, puis stream live.
    Ping toutes les 15 s pour garder la connexion ouverte.
    """
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
                    item = await asyncio.wait_for(queue.get(), timeout=15)
                    yield {
                        "event": "agent-event",
                        "data": json.dumps(item, ensure_ascii=False),
                    }
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            await event_bus.unsubscribe(sub_id)

    return EventSourceResponse(gen())
