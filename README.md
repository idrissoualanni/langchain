# Agent Control Center — LangGraph + Ollama + FastAPI + React

Dashboard web complet pour superviser et contrôler un agent LangGraph :
chat réel avec tools animés, gestion utilisateurs/threads, persistance
SQLite officielle, logs temps réel et visualisation mémoire/checkpoints.

## Architecture

```
React (Vite / TS / Tailwind 4 / Framer Motion)   → http://localhost:5173
 │  /chat   /memory   /logs   + SSE /api/events
 ▼
FastAPI                                          → http://localhost:8000
 │  users · threads · chat · chat/stream · state · history · logs · health
 │  + WebSocket /ws/logs
 ▼
LangGraph create_agent (v1) + ToolEventMiddleware
 │  tools : additionner · calculer_longueur_texte · recherche_web
 ▼
SQLite (SqliteSaver officiel)                    backend/database/
 ├─ checkpoints.db  → state LangGraph persisté (messages, interaction_count)
 └─ app.db          → users + threads (UUID backend)
Logs JSON-lines                                   logs/agent.log
Ollama cloud                                      MODEL_OLLAMA dans .env
```

## Démarrage

### Backend

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Ouvrir http://localhost:5173 (le proxy Vite route `/api` vers :8000).

## Endpoints

| Méthode | Route | Rôle |
|---|---|---|
| POST | `/api/users` | Créer un utilisateur (UUID backend) |
| GET | `/api/users` | Lister les utilisateurs |
| GET | `/api/users/{user_id}` | Obtenir un utilisateur |
| POST | `/api/users/{user_id}/threads` | Créer un thread (UUID backend) |
| GET | `/api/users/{user_id}/threads` | Lister les threads d'un user |
| GET | `/api/threads/{thread_id}` | Infos d'un thread |
| POST | `/api/chat` | Envoyer un message (réponse complète) |
| GET | `/api/chat/stream` | Idem, stream SSE du pipeline |
| GET | `/api/threads/{thread_id}/state` | State courant (checkpointer) |
| GET | `/api/threads/{thread_id}/history` | Historique des checkpoints |
| GET | `/api/logs` | Logs structurés (filtres limit/level/event/thread_id) |
| GET | `/api/events` | **SSE temps réel** — tous les événements agent |
| WS | `/ws/logs` | WebSocket logs (alternative) |
| GET | `/api/health` | Statut ollama / langgraph / sqlite |

## Fonctionnement

### user_id / thread_id

- **UUID générés côté backend** — le frontend ne saisit jamais d'UUID.
- Un thread appartient à un user (`threads.user_id` FK).
- Sécurité : `thread_belongs_to_user()` bloque tout accès croisé (403).
- Le frontend ne conserve jamais le thread d'un autre user (reset au changement).

### SQLite Checkpointer (mécanisme officiel LangGraph)

`SqliteSaver(conn)` sur `database/checkpoints.db` — la mémoire de
conversation est gérée **entièrement par LangGraph** via
`config = {"configurable": {"thread_id": ...}}`. Aucune persistance
manuelle des messages. Redémarrez le backend : l'historique et la
mémoire de l'agent sont intacts.

### Logs

`log_event()` écrit du JSON-lines dans `logs/agent.log` **et** publie
sur le bus temps réel (SSE + WS). Événements : RUN_START, STATE_LOAD,
USER_MESSAGE, TOOL_START, TOOL_END, TOOL_ERROR, ASSISTANT_MESSAGE,
CHECKPOINT_SAVED, RUN_END, USER_CREATE, THREAD_CREATE, ERROR…

### Animations des tools (événements réels uniquement)

`ToolEventMiddleware.wrap_tool_call` intercepte **chaque exécution
réelle** : TOOL_START → carte RUNNING (pulse + spinner) ; TOOL_END →
SUCCESS (check animé + durée) ; TOOL_ERROR → ERROR (rouge + message).
Le tool qui échoue retourne un ToolMessage d'erreur au LLM : l'agent
poursuit la conversation sans crash.

## Procédure de test (les 10 tests du brief)

1. **Créer User A** — modal "New User" (sidebar ou /chat) → UUID auto, user actif.
2. **Créer Thread A1** — "New Thread" → UUID, lié à A, thread actif.
3. **Envoyer "Bonjour"** → réponse du tuteur Python, message persisté.
4. **"Utilise l'outil additionner pour calculer 25 + 17."** → ToolExecutionCard RUNNING→SUCCESS, résultat 42 ; TOOL_START/TOOL_END visibles dans /logs et l'Agent Activity.
5. **Fermer le backend, redémarrer, recharger A1** → messages et checkpoints intacts (vérifié : l'agent se souvient du calcul précédent).
6. **Créer User B + Thread B1** → aucun historique de A ; API : 403 si B tente le thread de A.
7. **/logs** → streaming temps réel, filtres (INFO/WARNING/ERROR/TOOL/THREAD/STATE), recherche, pause/reprise, clear local.
8. **/memory** → stats, timeline des checkpoints, mode Raw State.
9. **Animations RUNNING → SUCCESS** → réelles (SSE TOOL_START/TOOL_END).
10. **Tool en erreur** → RUNNING → ERROR rouge (exception convertie en ToolMessage ; TOOL_ERROR loggé level=ERROR).

## Structure

```
backend/app/
├── main.py              # FastAPI + lifespan + routes
├── config.py            # env, chemins, health checks
├── agent/               # state, tools, middleware, graph, runner, prompts
├── db/                  # connections (app.db), users, threads
├── api/                 # schemas + routes (users, threads, chat, memory, logs, health)
├── logging/             # events (bus + JSON-lines), sse
└── ws/                  # WebSocket /ws/logs

frontend/src/
├── api/                 # base, users, threads, agent (stream), memory, logs, events (SSE)
├── hooks/               # useChat, useSelection, useUsers, useThreads, useMemory, useLogs, useHealth
├── components/
│   ├── layout/          # Sidebar, StatusBadge
│   ├── chat/            # ChatInput, MessageBubble, CreateThreadModal
│   ├── tools/           # ToolExecutionCard, ToolStatusPanel
│   ├── users/           # CreateUserModal, UserSelector
│   ├── threads/         # ThreadSelector
│   └── ui/              # Button, Card, Badge, Dialog, Input
├── pages/               # ChatPage, MemoryPage, LogsPage
└── types/agent.ts
```

`ap.py` (CLI legacy) est conservé à la racine.
