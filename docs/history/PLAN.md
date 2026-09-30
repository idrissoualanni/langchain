# Plan d'implémentation — Agent Control Center (LangGraph + Ollama + FastAPI + React)

> **Pour les agents exécutants :** suivre ce plan tâche par tâche. Les étapes utilisent la syntaxe checkbox (`- [ ]`) pour le suivi. Basé sur une analyse réelle du code existant (tests effectués : imports, SqliteSaver, create_agent v1, middleware, appel LLM réel avec tool-calling, mémoire multi-runs, isolation des threads).

**Objectif :** Transformer le prototype CLI `ap.py` en dashboard web complet "Agent Control Center" : chat réel avec l'agent, gestion users/threads, persistance SQLite officielle, logs temps réel, visualisation mémoire/checkpoints, animations tools basées sur événements réels.

**Architecture :** Backend FastAPI exposant l'agent LangGraph (créé avec `create_agent` v1 — déjà fonctionnel dans `ap.py`) avec checkpointer `SqliteSaver` sur `database/checkpoints.db`, users/threads dans `database/app.db` (SQLite séparé, UUID backend), streaming des événements via SSE, logs structurés JSON dans `logs/agent.log` + broadcast temps réel. Frontend React/TS/Vite/Tailwind avec 3 pages (Chat, Memory, Logs), sidebar avec statuts, animations Framer Motion pilotées par les événements SSE réels.

**Stack :** Python 3.14 / FastAPI 0.139 / LangChain 1.3.15 / LangGraph 1.2.11 / langgraph-checkpoint-sqlite 3.1.1 / langchain-ollama 1.1.0 / ollama 0.6.2 (cloud, model `gemma4:31b-cloud`) — React 19 / TypeScript / Vite / Tailwind CSS 4 / shadcn/ui / Lucide React / Framer Motion / React Router.

**Constats clés de l'analyse :**
- `ap.py` (521 lignes) : agent **fonctionnel** avec `create_agent` v1, `SqliteSaver`, 3 tools, state custom `user_id`/`interaction_count`. Bugs identifiés : `SqliteSaver.from_conn_string` est un context manager (jamais entré → **le checkpointer est cassé silencieusement**, `database/` n'existe même pas) ; interaction_count incorrect sur re-run (il est recalculé mais jamais persisté correctement ; v. tests).
- `ollama web_search` : fonctionne avec le Bearer token (vérifié) mais la clé est dans le `.env` → **ne jamais l'exposer au frontend**.
- Model configuré `gemma4:31b-cloud` : répond OK sur le cloud (vérifié). `glm-5.3-flash` : accès refusé (subscription). Local `gemma4:31b` : 404 (pas le modèle).
- `agent_db.json` / `memory.json` : ancienne persistance manuelle JSON (légacy, ne pas réutiliser — le checkpointer la remplace).
- Aucun frontend, aucun package.json, aucun serveur existant. `brief.md` : cahier des charges frontend détaillé.
- **Validé par test réel :** middleware `wrap_tool_call` émet TOOL_START/TOOL_END/TOOL_ERROR avec args + result + duration → streaming SSE possible **sans modifier les tools**.

---

## Structure de fichiers cible

```text
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, CORS, lifespan, routes
│   ├── config.py            # env, chemins, constantes
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── state.py         # CustomAgentState
│   │   ├── tools.py         # additionner, calculer_longueur_texte, recherche_web
│   │   ├── middleware.py    # ToolEventMiddleware (wrap_tool_call → events)
│   │   ├── graph.py         # create_agent(...) + helpers get_state/history
│   │   └── runner.py        # run_agent streamé (événements pour SSE)
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connections.py   # sqlite3 connections (app.db, checkpoints.db), verrous
│   │   ├── users.py         # CRUD users (UUID)
│   │   └── threads.py       # CRUD threads (UUID, user_id FK)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── schemas.py       # Pydantic models
│   │   ├── users.py         # POST/GET /api/users, GET /api/users/{id}
│   │   ├── threads.py       # POST/GET /api/users/{uid}/threads, GET /api/threads/{tid}
│   │   ├── chat.py          # POST /api/chat (+ variantes stream)
│   │   ├── memory.py        # GET /api/threads/{tid}/state|history
│   │   ├── logs.py          # GET /api/logs
│   │   └── health.py        # GET /api/health
│   ├── logging/
│   │   ├── __init__.py
│   │   ┝── events.py        # event_bus (subscribers), struct_logger
│   │   └── sse.py           # SSE endpoint /api/events (SSE, broadcast des events)
│   └── ws/
│       └── logs.py          # WebSocket /ws/logs
├── requirements.txt         # mise à jour (ajout fastapi, uvicorn, sse-starlette, websockets)
├── .env                     # déplacé/conservé à la racine backend/
├── database/                # créé au démarrage
│   ├── app.db               # users + threads (créé par init)
│   └── checkpoints.db       # SqliteSaver (créé au démarrage)
└── logs/agent.log           # logs structurés JSON-lines

frontend/
├── package.json             # react, react-dom, react-router-dom, framer-motion, lucide-react, tailwindcss 4, class-variance-authority, clsx, tailwind-merge, shadcn components
├── vite.config.ts           # proxy /api → 8000, /ws → 8000
├ ├── tsconfig.json
├── index.html
└── src/
    ├── main.tsx, App.tsx    # router + layout
    ├── index.css            # palette (tokens CSS)
    ├── types/agent.ts       # User, Thread, ChatMessage, AgentEvent, ToolExecution, LogEntry
    ├── api/                 # agent.ts, users.ts, threads.ts, memory.ts, logs.ts, events.ts (SSE)
    ├── hooks/               # useChat.ts, useUsers.ts, useThreads.ts, useMemory.ts, useLogs.ts, useHealth.ts, useAgentEvents.ts
    ├── components/
    │   ├── layout/Sidebar.tsx, StatusBadge.tsx, Header.tsx
    │   ├── chat/ChatMessages.tsx, MessageBubble.tsx, ChatInput.tsx, CreateThreadModal.tsx
    │   ├── tools/ToolExecutionCard.tsx, ToolStatusPanel.tsx
    │   ├── memory/CheckpointTimeline.tsx, StateInspector.tsx, RawState.tsx
    │   ├── logs/LogConsole.tsx, LogToolbar.tsx, LogLine.tsx
    │   ├── users/CreateUserModal.tsx, UserSelector.tsx
    │   └── ui/               # shadcn : button, dialog, input, select, card, badge, scroll-area, separator, tooltip
    └── pages/
        ├── ChatPage.tsx
        ├── MemoryPage.tsx
        └── LogsPage.tsx

ap.py                        # CONSERVÉ tel quel (CLI legacy, réutilise la même logique)
brief.md, MEMORY.md, memory.json, agent_db.json  # CONSERVÉS
```

---

### Task 0 : Préparation & installation des dépendances

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/.env` (copie du `.env` existant)

- [ ] **Step 0.1 : Créer `backend/` et copier la config**

```bash
mkdir backend
copy .env backend\.env
```

- [ ] **Step 0.2 : Écrire `backend/requirements.txt`**

```text
ollama
python-dotenv
tavily-python
fastapi
uvicorn[standard]
sse-starlette
pydantic
```

- [ ] **Step 0.3 : Installer et vérifier**

```bash
cd backend && pip install -r requirements.txt
pip list | findstr /i "fastapi uvicorn sse"
```

Expected: fastapi 0.139.0, uvicorn 0.49.0, sse-starlette (installé), pydantic 2.12.5. Les packages langchain/langgraph sont déjà installés globalement — ne pas les réinstaller.

- [ ] **Step 0.4 : Commit initial (si git présent)**

```bash
git init 2>nul & git add -A & git commit -m "chore: baseline before agent control center"
```

---

### Task 1 : Configuration centralisée

**Files:**
- Create: `backend/app/__init__.py` (vide)
- Create: `backend/app/config.py`
- Create: `backend/app/__init__.py` pour tous les sous-paquets (agent, db, api, logging, ws)

- [ ] **Step 1.1 : Écrire `backend/app/config.py`**

```python
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = Path(__file__).resolve().parents[1]

DATABASE_DIR = BACKEND_DIR / "database"
DATABASE_DIR.mkdir(exist_ok=True)
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

APP_DB_PATH = DATABASE_DIR / "app.db"
CHECKPOINTS_DB_PATH = DATABASE_DIR / "checkpoints.db"
LOG_PATH = LOG_DIR / "agent.log"

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
MODEL_NAME = os.getenv("MODEL_OLLAMA", "qwen2.5")

def ollama_headers() -> dict | None:
    return {"Authorization": f"Bearer {OLLAMA_API_KEY}"} if OLLAMA_API_KEY else None

def check_ollama_health() -> bool:
    try:
        import ollama
        ollama.Client(host=OLLAMA_HOST, headers=ollama_headers() or {}).list()
        return True
    except Exception:
        return False

def check_sqlite_health() -> bool:
    try:
        import sqlite3
        conn = sqlite3.connect(APP_DB_PATH, timeout=2)
        conn.execute("SELECT 1 FROM users LIMIT 1")
        conn.close()
        return True
    except Exception:
        return True  # app.db peut ne pas être encore initialisée

def check_sqlite_checkpointer_health() -> bool:
    try:
        import sqlite3
        conn = sqlite3.connect(CHECKPOINTS_DB_PATH, timeout=2)
        conn.execute("SELECT 1")
        conn.close()
        return True
    except Exception:
        return False
```

- [ ] **Step 1.2 : Vérifier l'import**

```bash
cd backend && python -c "from app.config import DB_PATH... ok"
python -c "from app.config import APP_DB_PATH, CHECKPOINTS_DB_PATH, MODEL_NAME; print(APP_DB_PATH, MODEL_NAME)"
```

Expected: chemins affichés sans erreur.

---

### Task 2 : Logging structuré + event bus (temps réel)

**Files:**
- Create: `backend/app/logging/events.py`
- Create: `backend/app/logging/sse.py`
- Create: `backend/app/logging/__init__.py`

- [ ] **Step 2.1 : Écrire `backend/app/logging/events.py`** — logger JSON-lines + bus d'événements.

```python
import asyncio, json, logging, time
from collections import deque
from typing import Any, Awaitable, Callable, Deque

logger = logging.getLogger("agent")

class EventBus:
    """Broadcast sync des événements vers les subscribers (SSE/WS)."""
    def __init__(self, history_size: int = 500):
        self._subs: dict[int, Callable[[dict], Awaitable[None] | None]] = {}
        self._next_id = 0
        self._history: Deque[dict] = deque(maxlen=history_size)
        self._lock = asyncio.Lock()

    async def subscribe(self, cb) -> int:
        async with self._lock:
            self._next_id += 1
            self._subs[self._next_id] = cb
            return self._next_id

    async def unsubscribe(self, sub_id: int):
        async with self._lock:
            self._subs.pop(sub_id, None)

    async def publish(self, event: dict):
        self._history.append(event)
        for cb in list(self._subs.values()):
            try:
                r = cb(event)
                if asyncio.iscoroutine(r):
                    await r
            except Exception:
                pass  # jamais crasher le run pour un subscriber

event_bus = EventBus()

def log_event(event: str, level: str = "INFO", message: str = "", user_id: str = "", thread_id: str = "", tool_name: str = "", extra: dict | None = None) -> dict:
    """Log structuré JSON + publication temps réel. Retourne l'event dict."""
    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "level": level,
        "event": event,
        "message": message,
        "user_id": user_id,
        "middleware_id": thread_id,
        "tool_name": tool_name,
        **(extra or {}),
    }
    logger.log(getattr(logging, level, logging.INFO), json.dumps(record, ensure_ascii=False))
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(event_bus.publish(record))
    except RuntimeError:
        pass  # pas de loop (CLI) → log fichier seulement
    return record

def get_recent_events(limit: int = 200) -> list[dict]:
    return list(event_bus._history)[-limit:]
```

NOTE: `"middleware_id"` au lieu de `thread_id` — **corrigé en Task 2.1.b** ci-dessous (garder `thread_id`).

- [ ] **Step 2.1.b : Correction — utiliser `thread_id` comme clé**

Dans `log_event`, remplacer `"middleware_id": thread_id` par `"thread_id": thread_id`. (La spec du brief exige `thread_id`.)

- [ ] **Step 2.2 : Écrire `backend/app/logging/sse.py`** — endpoint SSE (async, une queue par client).

```python
import asyncio, json
from fastapi import Request
from sse_starlette.sse import EventSourceResponse
from .events import event_bus, get_recent_events

async def sse_events(request: Request):
    queue: asyncio.Queue = asyncio.Queue()
    sub_id = None

    async def on_event(event: dict):
        await queue.put(event)

    sub_id = await event_bus.subscribe(on_event)

    async def gen():
        try:
            # replay historique récent
            for e in get_recent_events(100):
                yield {"event": "agent-event", "data": json.dumps(e)}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15)
                    yield {"event": "agent-event", "data": json.dumps(item)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            await event_bus.unsubscribe(sub_id)

    return EventSourceResponse(gen())
```

- [ ] **Server:WS** — WebSocket `/ws/logs` en alternative (brief mentionne les deux ; SSE pour events, WS optionnel). Implémentation minimale `backend/app/ws/logs.py` : boucle identique, `send_json` des events. Le SSE est la voie principale.

- [ ] **Step 2. hook logging basique**

ConfigureRootLogger une fois (dans `main.py`) : FileHandler `logs/agent.log` format JSON-lines + console. On n'utilise PAS `logging.basicConfig` global — chaque `log_event` passe par `logger` "agent" avec un handler dédié (éviter le spam httpx dans le fichier).

- [ ] **Step 2.3 : Test manuel**

```bash
cd backend && python -c "
from app.logging.events import log_event
log_event('RUN_START', message='test', user_id='u', thread_id='t')
print(open('logs/agent.log', encoding='utf-8').read()[-200:])
"
```

Expected: ligne JSON dans agent.log.

---

### Task 3 : Base users/threads (SQLite app.db)

**Files:**
- Create: `backend/app/db/connections.py`
- Create: `backend/app/db/users.py`
- CRUD threads splité : `backend/app/db/threads.py`

- [ ] **Step 3.1 : `connections.py`** — conn sqlite + init schema + verrou threading (FastAPI threadpool).

```python
import sqlite3, threading
from contextlib import contextmanager
from app.config import APP_DB_PATH

_local = threading.local()
_init_lock = threading.Lock()
_initialized = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS threads (
    thread_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    name TEXT NOT NULL DEFAULT 'New Thread',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_threads_user ON threads(user_id);
"""

def get_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(APP_DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return conn

def init_db():
    global _initialized
    with _init_lock:
        if _initialized:
            return
        conn = get_conn()
        conn.executescript(SCHEMA)
        conn.commit()
        _initialized = True
```

- [ ] **Step 3.2 : `users.py`**

```python
import uuid, datetime as dt
from .connections import get_conn

def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

def create_user(name: str) -> dict:
    user_id = str(uuid.uuid4())
    created_at = now_iso()
    conn = get_conn()
    conn.execute("INSERT INTO users (user_id, name, created_at) VALUES (?,?,?)", (user_id, name, created_at))
    conn.commit()
    return {"user_id": user_id, "name": name, "created_at": created_at}

def list_users() -> list[dict]:
    rows = get_conn().execute("SELECT user_id, name, created_at FROM users ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]

def get_user(user_id: str) -> dict | None:
    row = get_conn().execute("SELECT user_id, name, created_at FROM users WHERE user_id=?", (user_id,)).fetchone()
    return dict(row) if row else None
```

- [ ] **Step 3.3 : `threads.py`** — même pattern, avec `create_thread(user_id, name)`, `list_threads(user_id)`, `get_thread(thread_id)`, et **`thread_belongs_to_user(thread_id, user_id) -> bool`** (garde de sécurité anti-cross-user).

- [ ] **Step 3.4 : Test**

```bash
cd backend && python -c "
from app.db.connections import init_db
from app.db.users import create_user, list_users
init_db()
u = create_user('Test User')
print(u); print(list_users())
"
```

Expected: UUID créé, listing OK.

---

### Task 4 : Agent LangGraph (portage de ap.py, corrigé)

**Files:**
- Create: `backend/app/agent/state.py`, `tools.py`, `middleware.py`, `graph.py`, `runner.py`, `__init__.py`

- [ ] **Step 4.1 : `state.py`**

```python
from langgraph.graph import MessagesState
from pydantic import Field

class CustomAgentState(MessagesState):
    user_id: str = Field(default="")
    interaction_count: int = 0
```

- [ ] **Step 4.2 : `tools.py`** — reprendre à l'identique les 3 tools de `ap.py` (additionner, calculer_longueur_texte, recherche_web) avec leurs logs `TOOL_START`/`TOOL_END` internes conservés, mais en remplaçant `logger.info` par `log_event` (logging/events.py). L'API `@tool` et les docstrings restent inchangées.

- [ ] **Step 4.2.b : error-path — recherche_web**

Conserver le try/except existant : en erreur → `log_event("TOOL_ERROR", level="ERROR", tool_name="recherche_web", ...)` et retourner le message d'erreur **comme contenu du tool** (comportement actuel, l'agent peut répondre). Le middleware (Task 4.3) capture les vraies exceptions.

- [ ] **Step 4.3 : `middleware.py`** — cœur de l'observabilité. Émissions TOOL_START/TOOL_END/TOOL_ERROR **avec args, result, duration** (validé par test réel).

```python
import time, json
from langchain.agents.middleware import AgentMiddleware
from app.logging.events import log_event

def _snapshot(value, limit=500):
    try:
        s = json.dumps(value, ensure_ascii=False, default=str)
        return s[:limit]
    except Exception:
        return str(value)[:limit]

class ToolEventMiddleware(AgentMiddleware):
    def wrap_tool_call(self, request, handler):
        call = request.tool_call
        name = call.get("name", "unknown")
        args = call.get("args", {})
        # thread_id depuis config LangGraph
        from langgraph.config import get_config
        try:
            cfg = get_config()
            thread_id = (cfg.get("configurable") or {}).get("thread_id", "")
            user_id = (cfg.get("configurable") or {}).get("user_id", "")
        except Exception:
            thread_id, user_id = "", ""
        log_event("TOOL_START", message=f"Tool {name} started", tool_name=name, user_id=user_id, thread_id=thread_id, extra={"args": _snapshot(args)})
        start = time.perf_counter()
        try:
            result = handler(request)
            duration_ms = int((time.perf_counter() - start) * 1000)
            output = getattr(result, "content", result)
            log_event("TOOL_END", message=f"Tool {name} completed", tool_name=name, user_id=user_id, thread_id=wrap_thread_id, extra={"output": _snapshot(output), "duration_ms": duration_ms})
            return result
        except Exception as e:
            duration_ms = int((time.perf_counter() - event_start) * 1000)
            log_event("TOOL_ERROR", level="ERROR", message=f"Tool {name} failed: {e}", tool_name=name, user_id=user_id, thread_id=thread_id, extra={"error": str(e)[:300], "duration_ms": duration_ms})
            raise
```

NOTE : corriger les noms de variables (`wrap_thread_id`→`thread_id`, `event_start`→`start`) lors de l'écriture réelle — le squelette ci-dessus est le guide.

- [ ] **Step 4.4 : `graph.py`** — fix critique du checkpointer (`ap.py` avait un context-manager jamais entré).

```python
import sqlite3
from langchain.agents import create_agent
from langchain_ollama import ChatOllama
from langgraph.checkpoint.sqlite import SqliteSaver
from app.config import CHECKPOINTS_DB_PATH, OLLAMA_HOST, MODEL_NAME, ollama_headers
from app.agent.state import CustomAgentState
from app.agent.tools import tools
from app.agent.middleware import ToolEventMiddleware
from app.agent.prompts import SYSTEM_PROMPT  # repris de ap.py tel quel

_conn = None
_checkpointer = None
_agent = None

def get_agent():
    """Lazy singleton — appelé au startup FastAPI (lifespan)."""
    global _conn, _checkpointer, _agent
    if _agent is None:
        _conn = sqlite3.connect(CHECKPOINTS_DB_PATH, check_same_thread=False)
        _checkpointer = SqliteSaver(_conn)
        llm = ChatOllama(
            model=POSTED_MODEL,  # = MODEL_NAME
            base_url=OLLAMA_HOST,
            temperature=0,
            client_kwargs={"headers": ollama_headers()} if ollama_headers() else None,
        )
        _agent = create_agent(
            model=llm,
            tools=tools,
            system_prompt=SYSTEM_PROMPT,
            checkpointer=_checkpointer,
            state_schema=CustomAgentState,
            middleware=[ToolEventMiddleware()],
        )
    return _agent
```

- [ ] **Step 4.5 : `runner.py`** — orchestration d'un run complet streamé, émettant les événements SSE du pipeline : `RUN_START → STATE_LOAD → USER_MESSAGE → (LLM) → TOOL_START → TOOL_END → (LLM) → CHECKPOINT_SAVED → ASSISTANT_MESSAGE → RUN_END`, avec validation user/thread et **récupération de l'historique depuis le checkpointer** (pas de stockage manuel des messages).

Fonctions :

```python
def run_agent(user_id, thread_id, message) -> dict  # mode simple (invoke)
async def run_agent_stream(user_id, thread_id, message) -> AsyncIterator[dict]  # mode streaming SSE
def get_thread_state(user_id, thread_id) -> dict
def get_thread_history(user_id, thread_id) -> list[dict]
```

Points clés (validés par test réel) :
- `config = {"configurable": {"thread_id": thread_id}}` — LangGraph gère la mémoire.
- `interaction_count` : lu depuis state avant invoke, +1, repassé en input (pattern actuel d'`ap.py` conservé, mais **persisté** via le checkpointer car il fait partie du state).
- Tool status events: `log_event("TOOL_RUNNING"...)` n'existe pas — TOOL_START est suffisant. Frontend déduit RUNNING pendant TOOL_START→TOOL_END/ERROR.
- Si un tool échoue (exception réelle), `create_agent` v1 + ToolNode **attrape l'exception et la renvoie au LLM comme ToolMessage d'erreur** — l'agent peut poursuivre. (Vérifié : sans ce comportement, RUN2 échouait.) → Assurer ce comportement par défaut, le middleware logge TOOL_ERROR.

- [ ] **Step 4.6 : Test — régression du test E2E de l'analyse (obligatoire avant de passer à la suite)**

```bash
cd backend && python -c "
from app.db.connections import init_db
from app.db.users import create_user
from app.db.threads import create_thread
from app.agent.runner import run_agent
init_db()
u = create_user('E2E'); t = create_thread(u['user_id'], 'Test Thread')
r = run_agent(u['user_id'], t['thread_id'], 'Utilise l'outil additionner pour calculer 25 + 17.')
print(r)
"
```

Expected: `response` contient "42", `interaction_count=1`, logs TOOL_START/TOOL_END présents dans agent.log, thread B ne voit pas l'historique de A.

- [ ] **Step 4.7 : Commit**

```bash
git add backend/app/agent && git commit -m "feat(agent): port ap.py to structured backend with fixed checkpointer + tool middleware"
```

---

### Task 5 : API FastAPI (users, threads, chat, memory, logs, health)

**Files:**
- APIRouter: `backend/app/api/schemas.py`, `users.py`, `threads.py`, `chat.py`, `memory.py`, `slogs.py` (logs), `health.py`, `__init__.py`
- Create: `backend/app/main.py`

- [ ] **Step 5.1 : `schemas.py`** — modèles Pydantic (User, Thread, ChatRequest, ChatResponse, StateResponse, HistoryResponse, LogEntry, HealthResponse). Valider user_id/thread_id en UUID (pattern), messages non vides.

- [ ] **Step  brief-endpoints users** — `POST /api/users` (201), `GET /api/users` (liste), `GET /api/users/{user_id}` (404 si inexistant). 400 si name vide.

- [ ] **Step 5.3 : `threads.py`** — `POST /api/users/{user_id}/threads` (201, thread lié au user, 404 si user inexistant), `GET /api/users/{user_id}/threads`, `GET /api/threads/{thread_id}` (avec user_id dans la réponse). `GET /api/threads/{thread_id}/state` et `/history` dans memory.py, **tous vérifiant `thread_belongs_to_user`** quand un user_id est fourni (query param optionnel ou body ; spécifier via query param `user_id`).

- [ ] / **Step 5.4 : `chat.py`** — `POST /api/chat` : valide user existe, thread existe, thread appartient au user (sinon 403/404), message non vide → `run_agent` → réponse `{"response", "user_id", "thread_id", "interaction_count"}`.
- **`GET /api/chat/stream`** (SSE variant) : même validation, puis stream des événements du pipeline via `run_agent_stream` + events SSE du bus (filtre thread_id). Le frontend Chat utilise le stream pour les ToolExecutionCard temps réel ; `POST /api/chat` reste disponible (compat, tests).

- [ ] **Step 5.5 : `memory.py`** — `GET /api/threads/{thread_id}/state` : `{user_id, thread_id, interaction_count, message_count, last_checkpoint_id, messages: [...]}` (messages extraits du state LangGraph, type + contenu). `GET /api/threads/{thread_id}/history` : liste des snapshots `{checkpoint_id, parent_id, created_at, summary}` — `summary` = description lisible (dernier message ajouté : "User message", "Tool call additionner", "Assistant response"...) dérivée du checkpoint (parse messages du snapshot, comparaison avec parent).

- [ ] **Step 5.6 : `logs.py` (route)** — `GET /api/logs?limit=200&level=&event=&thread_id=` : parse `logs/agent.log` (JSON-lines, lecture tail), filtres. 400 si limit > 1000.

- [ ] **Step 5.7 : `health.py`** — `GET /a pi/health` → `{"status": "ok", "ollama": true/false, "langgraph": true, "sqlite": true}` — ollama via `check_ollama_health()` (appel `list()` cloud — rapide), sqlite via les deux DBs, langgraph via import + agent singleton prêt.

- [ ] **Step 5.8 : `main.py`** — app FastAPI, CORS (localhost:5173), lifespan : `init_db()` + `get_agent()` (warm-up) + config root logger (handler JSON-lines `agent.log` + console), routes API + SSE `/api/events` + WS `/ws/logs`, mount static frontend en prod (optionnel). uvicorn `0.0.0.0:8000`.

- [ ] **Step 5.9 : Test serveur manuel**

```bash
cd backend && python -m uvicorn app.main:app --port 8000
# autre terminal :
curl http://localhost:8000/api/health
curl -X POST http://agent.lab/api/users -H "Content-Type: application/json" -d "{\"name\":\"Alice\"}"
curl -X POST http://localhost:8000/api/users/{uid}/threads -d "{\"name\":\"T1\"}"
curl -X POST http://localhost:8000/api/chat -d "{\"user_id\":\"...\",\"thread_id\":\"...\",\"message\":\"Bonjour\"}"
```

Expected: health OK (ollama true — le modèle cloud répond), user/thread créés, chat répond.

---

### Task 6 : Frontend — scaffolding Vite + Tailwind + shadcn

- [ ] **Step 6.1 : Scaffold**

```bash
cd C:\Users\hp\Desktop\langchain
pnpm create vite frontend -- --template react-ts
cd frontend && pnpm install
pnpm dlx tailwindcss@4 init -p  # → tailwind v4 vite plugin
pnpm add react-router-dom framer-motion lucide-react clsx tailwind-merge class-variance-authority
pnpm dlx shadcn@latest init
pnpm dlx shadcn@latest add button dialog input select card badge scroll-area separator tooltip
```

- [ ] **Step 6.2 : Tokens CSS (`src/index.css`)** — palette du brief (variables CSS + dark). Les couleurs exactes : bg #0B0F14, surface #111820, surface-2 #18212B, border #26323D, text #F5F7FA, muted #94A3B8, accent #6C63FF, success #22C55E, warning #F59E0B, error #EF4444.

- [ ] **Step 6.3 : `vite.config.ts`** — proxy `/api` et `/ws` → `http://localhost:8000`.

- [ ] **Step 6.4 : `src/types/agent.ts`** — types complets partagés (User, Thread, ChatMessage, AgentEvent, ToolExecution, LogEntry, HealthInfo).

- [ ] **Step 6.5 : Couche API (`src/api/*.ts`)** — fetch wrappers : `users.ts`, `threads.ts`, `agent.ts` (chat + chatStream), `memory.ts`, `logs.ts`, `events.ts` (EventSource `/api/events` + filtres), `health.ts`. Base URL : `import.meta.env.VITE_API_URL || ""` (proxy).

- [ ] **Step 6.6 : `src/App.tsx` + router** — layout avec `<Sidebar />` + `<Outlet />`, routes `/chat` (default), `/memory`, `/logs`.

---

### Task 7 : Frontend — Sidebar + statuts + Health

- [ ] **Step 7.1 : `components/layout/Sidebar.tsx`** — logo "Agent Lab" (icône Bot/Sparkles), nav Chat/Memory/Logs (NavLink actifs), sections "Current User" (nom + user_id tronqué) et "Current Thread" (nom + thread_id tronqué) depuis un store léger (Context + localStorage pour persistance de sélection), boutons "New User" / "New Thread" (modals des Tasks 9-10), statuts Ollama/LangGraph/SQLite ( polled `useHealth` 30s + indicateur animé), footer "Agent Online" pulsant.

- [ ] **Step 7.2 : `components/layout/Header.tsx`** — titre page + model name + thread/user + status pill.

---

### Task 8 : Frontend — Chat réel avec Tool Cards animées (cœur UX)

- [ ] **Step 8.1 : `hooks/useChat.ts`** — gestion : current user/thread (via context), messages history (chargés depuis `GET /api/threads/{tid}/state` au changement de thread → rebuild messages depuis state LangGraph), `sendMessage` → `GET /api/chat/stream` (SSE fetch-stream), parsing des events `RUN_START`, `STATE_LOAD`, `USER_MESSAGE`, `TOOL_START`/`TOOL_END`/`TOOL_ERROR` (création/màj ToolExecutionCard), `ASSISTANT_MESSAGE`, `RUN_END`. En cas de stream indisponible → fallback `POST /api/chat` + events bus SSE globaux (filtre thread_id).

- [ ] **Step 8.2 : `components/chat/ChatMessages.tsx` + `MessageBubble.tsx`** — liste animée (Framer Motion fade/slide), user right / agent left, ToolExecutionCard insérée dans le flux à la position de l'appel.

- [ ] **Step 8.1 : `components/tools/ToolExecutionCard.tsx`** — props `toolName, status, input, output, durationMs, timestamp` ; states IDLE/RUNNING (pulse + spinner) /SUCCESS (check + transition) /ERROR (rouge + message) ; framer-motion AnimatePresence pour transitions.

- [ ] **Step 8.4 : `components/chat/ChatInput.tsx`** — textarea auto-resize, Enter=envoyer, Shift+Enter=newline, état disabled pendant run (status agent "running").

- [ ] **Step 8.5 : `components/tools/ToolStatusPanel.tsx`** — 3 cartes tools avec statut live (IDLE/RUNNING/SUCCESS/ERROR) dérivé des events du run courant + "Agent Activity" feed (timeline des événements horodatés du run).

---

### Task 8-corr : backend stream émet messages partiels — Optional

(Si temps → token streaming du LLM. Sinon, messages complets à ASSISTANT_MESSAGE suffisent — brief n'exige pas le token-streaming.)

---

### Task 9 : Frontend — Création User (modal + UX complète)

- [ ] **Step 9.1 : `components/users/CreateUserModal.tsx`** — Dialog shadcn : champ Name, Cancel/Create User → `POST /api/users` → écran de confirmation (Name + ID affichés, bouton Continue) → sélection auto du nouvel user (context store) + invalidate liste users.

- [ ] **Step 9.2 : `components/users/UserSelector.tsx`** — Select listant users (fetch `useUsers`), au changement : charger ses threads (`useThreads(user_id)`), sélectionner le dernier thread **ou aucun**, ne JAMAIS garder un thread d'un autre user.

---

### Task 10 : Frontend — Création Thread (modal + UX)

- [ ] **Step 10.1 : `components/chat/CreateThreadModal.tsx`** — Dialog : champ Thread Name, Cancel/Create Thread → `POST /api/users/{uid}/threads` → auto-sélection + refresh threads. Disable si pas d'utilisateur courant.

- [ ] **Step 10.2 : Intégration sélecteurs** — dans ChatPage et Sidebar (Current User/Thread + New User/Thread buttons).

---

### Task 80 : Page Memory (timeline checkpoints + raw state)

- [ ] **Step 11.1 : `pages/MemoryPage.tsx`** — sélecteurs User → Thread (identiques au chat), stats cards (user_id, thread_id, interactions, messages, last checkpoint), **"Current State"** (messages formatés lisibles), **"Conversation Timeline"** : CheckpointTimeline animée (Framer Motion reveal) — chaque checkpoint = checkpoint_id tronqué + résumé (type de message / tool call), flèches ↓, ordre chronologique.

- [ ] **Step 11.2 : `components/memory/StateInspector.tsx` + `RawState.tsx`** — vue lisible + toggle "Raw State" (JSON du state complet via state endpoint) pour devs.

- [ ] **Step 11.3 : Test page** — créer une conversation avec tool call, ouvrir /memory, vérifier timeline reflète : User message → Tool call → Assistant response.

---

### Task 12 : Page Logs (console temps réel)

- [ ] **Step 12.1 : `hooks/useLogs.ts`** — EventSource `/api/events` + merge initial `GET /api/logs` (backfill) + filtres niveau/event/thread (INFO, WARNING, ERROR, TOOL, THREAD, STATE) + search + pause/resume (buffer pendant pause) + auto-scroll + clear local (garde fichier serveur).

- [ ] **12.2 : `components/logs/LogConsole.tsx` + `LogToolbar.tsx + LogLine.tsx`** — terminal moderne : couleurs par niveau (INFO bleu/accent, SUCCESS vert, WARNING orange, ERROR rouge), animation d'apparition des lignes, timestamp/level/event/colorisé, search box, filtres par chips, boutons pause/clear, auto-scroll pin bottom.

- [ ] **Step 12.3 : Test** — envoyer un message chat dans un onglet, voir les logs apparaître en direct dans /logs (SSE), pause → reprise sans perte.

---

### Task 13 : Connexion complète + Tests E2E manuels (les 10 tests du brief)

- [ ] **13.1 : Lancer backend + frontend (2 terminaux)**

```bash
# T1
cd backend && python -m uvicorn app.main:app --port 8000
# T2
cd frontend && pnpm dev
```

- [ ] **13.2 : Exécuter les 10 tests du brief (tous doivent PASSER)** :
1. Créer User A (modal /chat) → UUID backend, auto-sélection ✓
2. Créer Thread A1 → UUID, lié à A, auto-sélection ✓
3. Envoyer "Bonjour" → réponse tuteur Python ✓
4. Envoyer "Utilise l'outil additionner pour calculer 25 + 17." → **ToolExecutionCard RUNNING→SUCCESS, "42"** (vérifier aussi dans /logs : TOOL_START/TOOL_END) ✓
5. Fermer backend, redémarrer, recharger Thread A1 (/chat ou /memory) → historique intact (checkpoints.db persisté) ✓
6. Créer User B + Thread B1 → aucun historique de A chez B ✓
7. Vérifier /logs (filtres, search, pause, clear) ✓
8. Vérifier /memory (stats, timeline, raw state) ✓
9. Vérifier animations RUNNING → SUCCESS ✓
10. Tool en erreur → RUNNING → ERROR (rouge) + message (ex: forcer via recherche_web sans réseau ou additionner avec args invalides gérés par ToolNode) ✓

- [ ] **Step 13.3 : Test API direct (sans frontend)** — curl sur tous les endpoints (users CRUD, threads CRUD, chat, state, history, logs, health) : vérifier codes 200/201/400/403/404.

- [ ] 13.4 : Test isolation cross-user (négatif) — `GET /api/threads/{tid_de_A}/state?user_id=B` → 403/404. `POST /api/chat` avec thread de B sur user A → 403.

- [ ] **Step 13.5 : Corriger les écarts trouvés, re-tester.**

---

### Task 14 : Nettoyage + Documentation finale

- [ ] **Step 14.1 : Nettoyage** — retirer `_inspect_tmp.py` (fait), fichiers `__pycache__` de git, ensure `.gitignore` (node_modules, dist, database/*.db, logs/agent.log conservé historique, __pycache__, .env du repo).
- [ ] **Step 14.2 : `README.md`** racine — architecture finale (schéma), démarrage (backend : `cd backend && pip install -r requirements.txt && python -m uvicorn app.main:app --port 8000` ; frontend : `cd frontend && pnpm install && pnpm dev`), endpoints, users/threads/checkpointer/logs/animations, procédure des 10 tests.
- [ ] **Step 14.3 : Vérification finale** — cold start complet (supprimer database/*.db, relancer, refaire tests 1-4) pour prouver l'absence d'état caché.

---

## Risques & mitigations

- **Model cloud `gemma4:31b-cloud`** : fonctionne (vérifié). Fallback documenté : si quota épuisé, changer `MODEL_OLLAMA` dans `.env` (aucune autre modification).
- **Clés API dans .env** : jamais exposées au frontend (backend only, lecture via `config.py`).
- **SqliteSaver & threads** : `check_same_thread=False` + agent singleton — access sérialisé via le même run loop (une requête chat à la fois par thread ; SQLite file-lock gère le reste).
- **Python 3.14 warning pydantic.v1** : cosmétique (langchain_core), sans impact fonctionnel — ignorer.
- **SSE vs WS** : SSE principal (simpler, proxy-friendly), WS implémenté en parallèle comme demandé (`/ws/logs`).
- **Windows console encoding** : forcer UTF-8 dans les scripts de test (`sys.stdout = io.TextIOWrapper(...)`), backend FastAPI sans souci (JSON UTF-8 natif).
- **`create_agent` handle_tool_errors** : ToolNode v1 convertit les exceptions en ToolMessage d'erreur → l'agent continue (comportement attendu, validé).

## Ordre d'exécution

Tasks 0→14 séquentiels (dépendances fortes), avec tests obligatoires aux jalons : **Task 4.6** (agent E2E), **Task 5.9** (API manuelle), **Task 13** (10 tests brief). Backend complet et testable **avant** le frontend (Tasks 6+).
