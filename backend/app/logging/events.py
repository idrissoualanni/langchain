# Logging structuré + event bus temps réel
import asyncio
import json
import logging
import queue
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Awaitable, Callable, Deque

from app.config import LOG_PATH

logger = logging.getLogger("agent")

# Seuls les événements de monitoring pertinent pour l'admin sont
# persistés en base : les battements internes à très haute fréquence
# ( ou purement techniques du démarrage ) seraient du bruit coûteux.
_EVENTS_SKIPPED_FOR_DB = {
    "LOG",
    "RAW",
}


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


# ==================================================================
# MONITORING ADMIN — persistance des événements dans Neon
# ( table agent_events ). File bornée + thread dédié + batchs :
# log_event ne bloque JAMAIS le run agent ; en cas de saturation ou
# d'indisponibilité DB on DROPPE ( compteur tracé ) plutôt que de
# ralentir l'application.
# ==================================================================
_event_queue: "queue.Queue[dict]" = queue.Queue(maxsize=2000)
_events_dropped = 0
_writer_started = False
_writer_lock = threading.Lock()


def _db_writer_loop() -> None:
    """Boucle du thread écrivain : batch INSERT toutes les ~1 s."""
    import os

    from sqlalchemy import create_engine, text

    from app.infrastructure.database.persistence import (
        _postgres_url as _pg_url,
    )

    global _events_dropped
    engine = None
    try:
        engine = create_engine(
            _pg_url(), pool_pre_ping=True, pool_size=1
        )
    except Exception:
        engine = None

    while True:
        batch: list[dict] = []
        try:
            batch.append(_event_queue.get(timeout=1.0))
        except queue.Empty:
            pass
        # Draine tout ce qui est déjà en file ( jusqu'à 200 par batch ).
        while len(batch) < 200:
            try:
                batch.append(_event_queue.get_nowait())
            except queue.Empty:
                break

        if not batch:
            continue

        if engine is None:
            try:
                engine = create_engine(
                    _pg_url(), pool_pre_ping=True, pool_size=1
                )
            except Exception:
                _events_dropped += len(batch)
                continue

        rows = [
            {
                "lv": e.get("level", "INFO"),
                "ev": e.get("event", "LOG"),
                "uid": str(e.get("user_id", "") or "")[:120],
                "tid": str(e.get("thread_id", "") or "")[:120],
                "tname": str(e.get("tool_name", "") or "")[:120],
                "msg": str(e.get("message", "") or "")[:2000],
                "ex": json.dumps(
                    {
                        k: v
                        for k, v in e.items()
                        if k
                        not in (
                            "timestamp",
                            "level",
                            "event",
                            "user_id",
                            "thread_id",
                            "tool_name",
                            "message",
                        )
                    },
                    ensure_ascii=False,
                    default=str,
                )[:8000],
            }
            for e in batch
            if e.get("event") not in _EVENTS_SKIPPED_FOR_DB
        ]
        if not rows:
            continue
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO agent_events "
                        "(level, event, user_id, thread_id, tool_name, "
                        " message, extra) "
                        "VALUES (:lv, :ev, :uid, :tid, :tname, :msg, "
                        " CAST(:ex AS jsonb))"
                    ),
                    rows,
                )
        except Exception:
            # DB injoignable : on lâche le batch ( compteur ) — jamais
            # de blocage, jamais de crash du thread.
            _events_dropped += len(rows)
            try:
                engine.dispose()
            except Exception:
                pass
            engine = None


def start_event_persistence() -> None:
    """Démarre le thread écrivain ( au startup FastAPI lifespan )."""
    global _writer_started
    with _writer_lock:
        if _writer_started:
            return
        threading.Thread(
            target=_db_writer_loop,
            name="agent-events-writer",
            daemon=True,
        ).start()
        _writer_started = True


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

    # Persistance monitoring ( thread-safe, jamais bloquante ) : la
    # file est bornée — saturée, on droppe ( compteur ) plutôt que de
    # ralentir le run agent.
    global _events_dropped
    try:
        _event_queue.put_nowait(dict(record))
    except queue.Full:
        _events_dropped += 1

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
