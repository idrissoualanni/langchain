# Logging structuré + event bus temps réel
import asyncio
import json
import logging
import time
from collections import deque
from pathlib import Path
from typing import Any, Awaitable, Callable, Deque

from app.config import LOG_PATH

logger = logging.getLogger("agent")


def setup_logging() -> None:
    """Configure le logger 'agent' : JSON-lines dans agent.log + console.

    À appeler une seule fois au startup (main.py lifespan).
    """
    if logger.handlers:
        return

    logger.setLevel(logging.INFO)

    class JsonLineFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            # log_event passe déjà un dict JSON sérialisé dans record.msg
            if isinstance(record.msg, dict):
                return json.dumps(record.msg, ensure_ascii=False)
            return json.dumps(
                {
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "level": record.levelname,
                    "event": "LOG",
                    "message": str(record.msg),
                },
                ensure_ascii=False,
            )

    formatter = JsonLineFormatter()

    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


class EventBus:
    """Bus d'événements : publie chaque event vers les subscribers SSE/WS.

    Conserve un historique borné pour le backfill des nouveaux clients.
    """

    def __init__(self, history_size: int = 500):
        self._subs: dict[
            int, Callable[[dict], Awaitable[None] | None]
        ] = {}
        self._next_id = 0
        self._history: Deque[dict] = deque(maxlen=history_size)
        self._lock = asyncio.Lock()

    async def subscribe(self, cb: Callable[[dict], Any]) -> int:
        async with self._lock:
            self._next_id += 1
            self._subs[self._next_id] = cb
            return self._next_id

    async def unsubscribe(self, sub_id: int) -> None:
        async with self._lock:
            self._subs.pop(sub_id, None)

    async def publish(self, event: dict) -> None:
        self._history.append(event)
        for sub_id, cb in list(self._subs.items()):
            try:
                result = cb(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                # Un subscriber défaillant ne doit jamais casser un run
                # agent. On ne l'avale cependant pas silencieusement :
                # sans ce log, une connexion SSE/WS morte est invisible
                # ( le flux semble vivant, plus rien n'arrive ).
                logger.warning(
                    "event_bus subscriber %s a échoué",
                    sub_id,
                    exc_info=True,
                )

    def recent(self, limit: int = 200) -> list[dict]:
        """Historique récent pour le backfill SSE/WS.

        API publique stable — les callers ne doivent PAS lire
        ``event_bus._history`` directement ( attribut privé : un
        refactor du deque casserait le backfill SSE ET WS ).
        """
        return list(self._history)[-limit:]


event_bus = EventBus()

# Loop asyncio de l'app (capturée au startup FastAPI). log_event peut
# être appelé depuis un thread executor (middleware tool) où il n'y a
# pas de running loop — on publie alors via cette loop thread-safe.
_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


def log_event(
    event: str,
    level: str = "INFO",
    message: str = "",
    user_id: str = "",
    thread_id: str = "",
    tool_name: str = "",
    extra: dict | None = None,
) -> dict:
    """Émet un événement : log JSON dans agent.log + broadcast temps réel.

    Retourne l'event dict (utilisé par le streaming SSE).
    """
    record: dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "level": level,
        "event": event,
        "user_id": user_id,
        "thread_id": thread_id,
        "tool_name": tool_name,
        "message": message,
    }
    if extra:
        record.update(extra)

    logger.log(
        getattr(logging, level, logging.INFO),
        record,
    )

    # Broadcast temps réel (thread-safe) :
    # 1) loop principale enregistrée (middleware appelé dans executor)
    # 2) sinon running loop courante (contexte async direct)
    loop = _main_loop
    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

    # Au shutdown, la loop référencée peut être fermée mais encore
    # présente : call_soon_threadsafe lève alors RuntimeError ( "Event
    # loop is closed" ). On perd les derniers events — sans crasher.
    if loop is not None and not loop.is_closed() and loop.is_running():
        try:
            loop.call_soon_threadsafe(
                _schedule_publish, dict(record)
            )
        except RuntimeError:
            pass

    return record


def _schedule_publish(event: dict) -> None:
    """Planifie la publication sur la loop (appelé via call_soon_threadsafe)."""
    task = asyncio.ensure_future(event_bus.publish(event))
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)


_pending_tasks: set[asyncio.Task] = set()


def get_recent_events(limit: int = 200) -> list[dict]:
    """Historique récent des événements (backfill SSE/WS).

    Délégué à l'API publique EventBus.recent() — conservée pour
    rétrocompatibilité ( tests, autres modules ).
    """
    return event_bus.recent(limit)


def read_log_file(limit: int = 200) -> list[dict]:
    """Lecture tail du fichier agent.log (JSON-lines), plus récents en dernier.

    Retourne les lignes non-JSON en événements bruts pour ne rien perdre.
    """
    path = Path(LOG_PATH)
    if not path.exists():
        return []

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    events: list[dict] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append(
                {
                    "timestamp": "",
                    "level": "INFO",
                    "event": "RAW",
                    "message": line[:500],
                }
            )
    return events
