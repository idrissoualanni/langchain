# WebSocket /ws/logs — alternative temps réel au SSE
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.logging.events import event_bus, get_recent_events

router = APIRouter()


@router.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket):
    """Diffuse tous les événements agent en temps réel via WebSocket.

    Le client reçoit d'abord un backfill des 100 derniers events,
    puis chaque nouvel événement en message JSON.
    """
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
