# WebSocket /ws/logs — alternative temps réel au SSE
#
# Mission Identité (§22) : réservé ADMIN. Le protocole WebSocket
# navigateur ne peut pas poser d'headers custom → le token passe
# en query `?auth=<token>` : PREUVE vérifiée ( CurrentUserResolver
# , signature réelle en mode clerk ) , jamais une identité crue.
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth.resolver import _resolve_from_token
from app.logging.events import event_bus, get_recent_events

router = APIRouter()


@router.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket):
    """Diffuse les événements agent en temps réel — ADMIN.

    Le client reçoit d'abord un backfill des 100 derniers events,
    puis chaque nouvel événement en message JSON.
    """
    token = websocket.query_params.get("auth", "")
    if not token:
        await websocket.close(code=4401)
        return
    try:
        current = _resolve_from_token(token)
    except Exception:
        await websocket.close(code=4401)
        return
    if not current.is_admin:
        await websocket.close(code=4403)
        return

    await websocket.accept()
    queue: asyncio.Queue[dict] = asyncio.Queue()

    async def on_event(event: dict) -> None:
        await queue.put(event)

    sub_id = await event_bus.subscribe(on_event)

    try:
        # Backfill initial
        for event in get_recent_events(100):
            await websocket.send_json(event)

        while True:
            item = await queue.get()
            await websocket.send_json(item)

    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception:
        pass
    finally:
        await event_bus.unsubscribe(sub_id)
