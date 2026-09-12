# RAPPORT — Agent Control Center (LangGraph + Ollama)

**Date :** 9 septembre 2026
**Projet :** Transformation du prototype CLI `ap.py` en dashboard web complet de supervision d'agent IA, puis ajout d'une **mémoire longue durée cross-thread**.

---

## 1. Point de départ (existant)

Avant ce travail, le dossier contenait :

| Élément | État |
|---|---|
| `ap.py` (521 lignes) | Prototype CLI — agent LangGraph `create_agent` v1 avec 3 tools, **mais checkpointer cassé silencieusement** (context-manager jamais entré → **aucune persistance réelle**) |
| `agent_db.json`, `memory.json` | Ancienne persistance manuelle JSON (legacy, remplacée par le checkpointer) |
| `logs/agent.log` | Logs texte plat, non structurés |
| `brief.md` | Cahier des charges frontend détaillé (non implémenté) |
| `requirements.txt` | 3 lignes (ollama, dotenv, tavily) |
| Frontend | **Inexistant** (aucun package.json) |
| Backend web / API | **Inexistant** |

**Réutilisé tel quel :** les 3 tools (`additionner`, `calculer_longueur_texte`, `recherche_web`), le system prompt tuteur Python, le state custom (`user_id`, `interaction_count`), la config Ollama cloud (`.env`), l'API moderne `create_agent` (LangChain v1 — pas l'ancien `create_react_agent`).

---

## 2. Architecture finale

```
React 19 + TypeScript + Vite + Tailwind 4 + Framer Motion     :5173
 │   /chat   /memory   /logs   + EventSource /api/events
 ▼  proxy Vite /api → :8000
FastAPI + uvicorn + sse-starlette                             :8000
 │   users · threads · chat · chat/stream (SSE) · state · history
 │   profile (GET/PUT) · logs · health · /api/events · /ws/logs
 ▼
LangGraph create_agent v1 + ToolEventMiddleware
 │   tools : additionner · calculer_longueur_texte · recherche_web
 │   memory : get_user_profile · update_user_profile
 ▼
DEUX SYSTÈMES DE STOCKAGE INDÉPENDANTS :
 ├── Checkpointer (SqliteSaver) — clé thread_id
 │     database/checkpoints.db → state de conversation
 └── Long-Term Store (SqliteStore) — clé user_id
       database/long_term_memory.db → profil utilisateur
         namespace ("users","profile",user_id) → {"name","description"}
 ▼
logs/agent.log (JSON-lines) + bus temps réel
Ollama cloud — gemma4:31b-cloud
```

---

## 3. Fichiers créés

### Backend — `backend/` (17 fichiers)

| Fichier | Rôle |
|---|---|
| `app/main.py` | App FastAPI, CORS, lifespan (logging + DB + agent warm-up + loop registration), montage des routes |
| `app/config.py` | Chemins, .env, headers Ollama (clé **jamais exposée** au frontend), health checks ollama/sqlite/langgraph |
| `app/agent/state.py` | `CustomAgentState` (MessagesState + user_id + interaction_count) |
| `app/agent/tools.py` | Les 3 tools repris d'`ap.py` + **2 tools mémoire** (`get_user_profile`, `update_user_profile`), loggés via `log_event` |
| `app/agent/prompts.py` | System prompt tuteur Python + **règles mémoire longue durée** (quand lire/écrire, distinction user_id/thread_id explicite) |
| `app/agent/middleware.py` | **Cœur observabilité + sécurité mémoire** : `wrap_tool_call` émet TOOL_START/TOOL_END/TOOL_ERROR — et **force le user_id réel de la config sur les tools mémoire** (isolation stricte, le LLM ne peut pas spéculer un autre user_id). `wrap_model_call` **injecte user_id + thread_id dans le system prompt** à chaque appel LLM |
| `app/agent/graph.py` | `create_agent(...)` singleton avec **`SqliteSaver(connexion directe)`** + **`store=SqliteStore`** (mémoire longue durée) |
| `app/agent/memory.py` | **NOUVEAU** — Store longue durée : `read_profile`/`write_profile` avec validation stricte (name/description uniquement), fusion partielle, logs MEMORY_*, verrou RLock, namespace `("users","profile",user_id)` |
| `app/agent/runner.py` | `run_agent` (synchrone), `run_agent_stream` (SSE), `get_thread_state`, `get_thread_history` avec résumés lisibles des checkpoints |
| `app/db/connections.py` | Connexions SQLite thread-safe (thread-local) + schema users/threads |
| `app/db/users.py` | CRUD users — **UUID générés backend** |
| `app/db/threads.py` | CRUD threads + **`thread_belongs_to_user()`** (garde anti-cross-user) |
| `app/api/schemas.py` | Validation Pydantic stricte : UUID, messages non vides, 404/403/422 propres |
| `app/api/users.py` | POST/GET `/api/users`, GET `/api/users/{id}` + **GET/PUT `/api/users/{id}/profile`** (lecture/écriture mémoire longue durée, champs name/description uniquement) |
| `app/api/threads.py` | POST/GET `/api/users/{id}/threads`, GET `/api/threads/{id}` |
| `app/api/chat.py` | POST `/api/chat` + GET `/api/chat/stream` (SSE pipeline complet) avec validation user/thread/propriété |
| `app/api/memory.py` | GET state + history (vérifient l'appartenance du thread) |
| `app/api/logs.py` | GET `/api/logs` (filtres limit/level/event/thread_id) |
| `app/api/health.py` | GET `/api/health` → ollama/langgraph/sqlite |
| `app/logging/events.py` | Logger JSON-lines + **EventBus** broadcast SSE/WS (thread-safe via loop enregistrée) |
| `app/logging/sse.py` | SSE `/api/events` avec backfill 100 derniers événements |
| `app/ws/logs.py` | WebSocket `/ws/logs` (alternative) |
| `requirements.txt` | + fastapi, uvicorn[standard], sse-starlette |

### Frontend — `frontend/` (33 fichiers)

| Fichier | Rôle |
|---|---|
| `src/types/agent.ts` | Types complets (User, Thread, ChatMessage, AgentEvent, ToolExecution, LogEntry, HealthInfo…) |
| `src/api/base.ts` | Fetch wrapper avec erreurs API propres |
| `src/api/users.ts` / `threads.ts` | CRUD |
| `src/api/agent.ts` | `sendChatMessage` + `streamChatMessage` (parse SSE frames + fallback) |
| `src/api/memory.ts` | State + history + **getUserProfile / updateUserProfile** (mémoire longue durée) |
| `src/api/logs.ts` | Logs + health |
| `src/api/events.ts` | Connexion EventSource `/api/events` (reconnexion auto) |
| `src/hooks/useSelection.tsx` | Contexte user/thread courant + localStorage + **reset du thread au changement d'utilisateur** (jamais un thread d'un autre) |
| `src/hooks/useChat.ts` | Historique depuis le checkpointer, envoi streamé, tool executions RUNNING→SUCCESS/ERROR depuis événements réels, activity feed |
| `src/hooks/useUsers.ts` / `useThreads.ts` / `useMemory.ts` / `useHealth.ts` | Hooks data correspondants (`useMemory` gère aussi le profil longue durée : load + update) |
| `src/hooks/useLogs.ts` | Console temps réel : backfill + SSE, pause avec buffer, filtres (INFO/WARNING/ERROR/TOOL/THREAD/STATE), recherche, clear local |
| `src/components/layout/Sidebar.tsx` | Nav Chat/Memory/Logs, **sélecteurs user/thread intégrés** (chargement auto + auto-sélection dernier thread), New User/New Thread, statuts Ollama/LangGraph/SQLite, indicateur Agent Online pulsant |
| `src/components/tools/ToolExecutionCard.tsx` | **Carte tool animée** : nom, statut, input, output, durée, timestamp — RUNNING (pulse + spinner), SUCCESS (check spring), ERROR (rouge + message) |
| `src/components/tools/ToolStatusPanel.tsx` | Statut live des 5 tools + Agent Activity (trace hiérarchique : tools/memory indentés sous le run, inclut MEMORY_READ/WRITE) |
| `src/components/memory/LongTermMemoryCard.tsx` | **NOUVEAU** — User Long-Term Memory : Name + Description, boutons Refresh / Edit (formulaire), badge cross-thread |
| `src/components/chat/MessageBubble.tsx` | Bulles user/agent animées |
| `src/components/chat/ChatInput.tsx` | Textarea auto, Entrée/Shift+Entrée, état running |
| `src/components/chat/CreateThreadModal.tsx` | Modal création thread + confirmation avec ID affiché |
| `src/components/users/CreateUserModal.tsx` | Modal création user + écran confirmation (Name + ID) + Continue |
| `src/components/users/UserSelector.tsx` / `threads/ThreadSelector.tsx` | Sélecteurs custom dark-mode |
| `src/components/ui/` | Button, Card, Badge, Dialog, Input (style shadcn adapté, zéro dépendance radix) |
| `src/pages/ChatPage.tsx` | Chat complet : header (model, statut), sélecteurs, conversation, tool cards, panel activité |
| `src/pages/MemoryPage.tsx` | **User Long-Term Memory** (profil cross-thread, refresh + edit) + Stats (IDs, interactions, messages, checkpoints), **timeline animée des checkpoints**, Current State lisible + **mode Raw State** |
| `src/pages/LogsPage.tsx` | Console terminal : couleurs par niveau/événement, recherche, filtres chips, pause/reprise, auto-scroll, clear |
| `src/App.tsx` | Router + layout + modals globaux |
| `src/index.css` | Palette exacte du brief (#0B0F14 → #EF4444) + animations CSS (pulse-dot, tool-pulse) |

### Racine

`PLAN.md` (plan d'implémentation), `README.md` (doc complète), `.gitignore`

---

## 4. Fichiers conservés sans modification

`ap.py` (CLI legacy), `brief.md`, `MEMORY.md`, `memory.json`, `agent_db.json` (legacy), `.env` (copié vers `backend/.env`)

---

## 5. Bugs corrigés

| Bug | Impact avant | Fix |
|---|---|---|
| **`SqliteSaver.from_conn_string()` jamais entré** (context-manager) | **Aucune persistance** — le dossier `database/` n'existait même pas ; l'agent perdait tout | `sqlite3.connect()` directe + `SqliteSaver(conn)` dans `graph.py` |
| **SSE dict au lieu de string** | `StreamingResponse` crashait silencieusement (`'dict' has no attribute 'encode'`) — 0 événement reçu | Yield de frames SSE textuelles (`event: X\ndata: {...}\n\n`) |
| **Event bus bloqué depuis threads executor** | TOOL events jamais broadcastés (le middleware tourne dans un thread sans loop asyncio) | Loop principale enregistrée au startup + `call_soon_threadsafe` |
| **Crash complet sur tool en erreur** | Une exception dans un tool tuait tout le run | Middleware convertit en `ToolMessage` d'erreur → l'agent poursuit + TOOL_ERROR loggé |
| **user_id absent des tool events** | Observabilité incomplète | `user_id` ajouté au `configurable` LangGraph, lu par le middleware |
| **Crash sur thread vide dans les tests** | `get_thread_state` retourne None | Géré côté API (state vide par défaut) |
| **Liste de threads jamais chargée** (bug UX) | Sélecteur de threads vide au démarrage — impossible de reprendre une conversation | `useEffect` de chargement automatique dans `useThreads` (charge à chaque changement d'utilisateur) |
| **SqliteStore : `cannot start a transaction within a transaction`** | Chaque écriture mémoire échouait — l'agent répondait mais le profil n'était jamais stocké | **Deux fixes** : (1) `store.setup()` obligatoire avant usage, (2) `conn.isolation_level = None` (autocommit) — le store gère ses propres BEGIN/COMMIT explicites, le mode auto-transaction de Python laissait une transaction ouverte après `setup()` |

---

## 6. Fonctionnement des mécanismes clés

- **user_id** : UUID backend à la création (`POST /api/users`). Le frontend ne saisit jamais d'UUID — modal Name → création → auto-sélection. Stocké dans app.db + propagé dans le state LangGraph et les événements.
- **thread_id** : UUID backend, lié au user (FK). Utilisé par LangGraph via `config = {"configurable": {"thread_id": ...}}`. Sécurité : `thread_belongs_to_user()` → 403 sur tout accès croisé ; le frontend reset le thread courant quand l'utilisateur change.
- **Checkpointer SQLite** : le mécanisme officiel — messages, user_id et interaction_count persistés/relus uniquement via LangGraph. **Aucune persistance manuelle des messages.**
- **Logs** : `log_event()` écrit du JSON-lines dans `agent.log` ET publie sur le bus temps réel (SSE + WS). Pipeline complet : RUN_START → STATE_LOAD → USER_MESSAGE → TOOL_START/END/ERROR → ASSISTANT_MESSAGE → CHECKPOINT_SAVED → RUN_END.
- **Animations tools** : uniquement des événements **réels** du backend (SSE). Aucune simulation. RUNNING = TOOL_START reçu, SUCCESS/ERROR = TOOL_END/TOOL_ERROR reçu.

### 6.1 Mémoire longue durée (NOUVEAU — v2)

**Deux systèmes indépendants, clairement séparés :**

| Système | Clé | Mécanisme | Fichier | Contenu |
|---|---|---|---|---|
| Conversation | `thread_id` | `SqliteSaver` (checkpointer) | `checkpoints.db` | messages, interaction_count |
| Profil utilisateur | `user_id` | `SqliteStore` (long-term store) | `long_term_memory.db` | `{"name", "description"}` |

**Flux de la mémoire :**
1. `wrap_model_call` injecte `user_id` + `thread_id` réels dans le system prompt à chaque appel LLM
2. L'agent décide d'appeler `get_user_profile`/`update_user_profile` (règles §11 du brief dans le prompt : lire si info personnelle utile, écrire si nom/description clairement donnés, jamais inventer, jamais mémoriser hors-profil)
3. `wrap_tool_call` **force** le user_id de la config sur les args — le LLM ne peut pas lire/écrire la mémoire d'un autre utilisateur même en spéculant un autre user_id
4. `write_profile` valide strictement (seuls `name` et `description` passent), fusionne avec l'existant (update partiel), écrit dans le namespace `("users", "profile", user_id)` avec la clé `"profile"`
5. Événements MEMORY_READ / MEMORY_WRITE (ou *_ERROR) → agent.log + SSE + frontend (trace Chat, console Logs, activity feed)

**Namespace :** `users/profile` — un namespace par utilisateur : `("users", "profile", "<user_id>")`.

**Isolation :** triple couche — namespace par user_id (un user ne voit structuralement que le sien), user_id forcé par le middleware (le LLM ne peut pas en changer), appartenance vérifiée API (404 si user inconnu).

---

## 7. Tests réalisés — tous PASS

| # | Test (brief) | Résultat |
|---|---|---|
| 1 | Créer User A depuis le frontend | ✅ 201, UUID backend, auto-sélection |
| 2 | Créer Thread A1 | ✅ 201, lié à A, auto-sélection |
| 3 | Envoyer « Bonjour » | ✅ Réponse tuteur Python, checkpoint persisté |
| 4 | « Utilise l'outil additionner pour calculer 25 + 17 » | ✅ Tool **réellement** appelé → 42, TOOL_START/TOOL_END loggés + broadcast SSE |
| 5 | **Fermer le backend, redémarrer, recharger A1** | ✅ 16 users, threads, 88 checkpoints intacts ; **l'agent se souvient du calcul précédent** (répond « 384 » à « quel était mon résultat ? ») |
| 6 | Créer User B + Thread B1 — isolation | ✅ B1 vide ; API → 403 si B tente le thread de A ; 404 user inexistant ; 422 message vide |
| 7 | Vérifier les logs | ✅ JSON-lines, filtres, recherche, pause/reprise, temps réel SSE |
| 8 | Vérifier /memory | ✅ Stats, timeline checkpoints animée, Raw State + **User Long-Term Memory (profil, refresh, edit)** |
| 9 | Animations RUNNING → SUCCESS | ✅ Pilotées par les vrais TOOL_START/TOOL_END SSE |
| 10 | Tool en erreur → RUNNING → ERROR | ✅ TOOL_ERROR level=ERROR avec tool_name/durée/message, l'agent poursuit sans crash |
| — | Pipeline SSE stream | ✅ 6 événements ordonnés : RUN_START → STATE_LOAD → USER_MESSAGE → ASSISTANT_MESSAGE → CHECKPOINT_SAVED → RUN_END |
| — | Bus SSE thread-safe | ✅ TOOL events broadcastés en direct avec thread_id + input |
| — | Compilation frontend | ✅ `tsc -b && vite build` — 2292 modules, 0 erreur |

### 7.1 Tests mémoire longue durée (NOUVEAU — v2) — tous PASS

Scénario exact du brief : User A (Mamadou, mécatronique) écrit son profil dans le Thread A1, puis lit depuis A2 ; User B (Fatou, biologie) doit être isolé.

| # | Test | Scénario | Résultat |
|---|---|---|---|
| M1 | Création | User A, Thread A1 : « Je m'appelle Mamadou. Je suis étudiant en mécatronique… » | ✅ L'agent appelle `update_user_profile` → `GET profile` : `name="Mamadou"`, `description="Étudiant en mécatronique qui aime apprendre en construisant des projets pratiques."` |
| M2 | Lecture même thread | Thread A1 : « Quel est mon nom ? » | ✅ « Ton nom est Mamadou. » (tool `get_user_profile` appelé) |
| M3 | **Cross-thread** (le test critique) | **Nouveau Thread A2** (même user), conversation neuve : « Qui suis-je ? » | ✅ « Tu es Mamadou, un étudiant en mécatronique qui aime apprendre en construisant des projets pratiques. » |
| M4 | **Persistance après redémarrage** | Backend **arrêté puis relancé**, Thread A2 : « Qui suis-je ? » | ✅ GET direct : profil intact ; l'agent répond correctement — le profil survit au redémarrage |
| M5 | User B — mémoire propre | User B, Thread B1 : « Je m'appelle Fatou. Je suis étudiante en biologie. » puis « Qui suis-je ? » | ✅ Profil B : `name="Fatou"`, `description="Étudiante en biologie"` ; réponse : « Tu es Fatou, et tu es étudiante en biologie. » |
| M6 | **Isolation stricte** | Réponse de B scrutée pour toute fuite de données de A | ✅ Aucune occurrence de « Mamadou » ni « mécatronique » dans la réponse de B ; profil A intact (non écrasé) |

**Le schéma critique du brief est validé :**

```
USER A ──┬── Thread A1 ── écrire profil  ── ✅
         └── Thread A2 ── lire profil    ── ✅ (Mamadou retrouvé)
USER B ──── Thread B1 ── lire profil     ── ✅ (Fatou uniquement, jamais Mamadou)
```

**Exemple de données réellement stockées** (via GET `/api/users/{id}/profile`) :

```json
{
  "user_id": "67a2e765-4213-4b53-be8f-2ee40fe942dd",
  "name": "Mamadou",
  "description": "Étudiant en mécatronique qui aime apprendre en construisant des projets pratiques.",
  "exists": true
}
```

**Événements mémoire observés dans agent.log :**
- `MEMORY_STORE_INIT` — au startup (fichier + namespace)
- `MEMORY_WRITE` — `user_id=…`, `namespace=users/profile`, `fields=name,description`
- `MEMORY_READ` — `user_id=…`, `operation=read`, `result=found/not_found`

---

## 8. Commandes

```bash
# Backend
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8000

# Frontend
cd frontend
npm install
npm run dev          # → http://localhost:5173
```

---

## 9. Limites connues et recommandations

- **Model cloud** : `gemma4:31b-cloud` (quota) — changer `MODEL_OLLAMA` dans `backend/.env` pour un autre modèle, aucune autre modification nécessaire.
- **Token streaming LLM** : les messages arrivent complets à ASSISTANT_MESSAGE (le brief n'exigeait pas le token-by-token).
- **`.env` contient des clés** : jamais exposées au frontend (lecture backend uniquement) ; ne pas committer (`.gitignore` en place).
- **Warning pydantic.v1 / Python 3.14** : cosmétique (langchain_core), sans impact fonctionnel.

### 9.1 Limites spécifiques à la mémoire longue durée (expérimentation v2)

- **Qualité de l'extraction** : l'agent (LLM) décide seul quand écrire le profil. Gemma reformule la description à sa manière (ex. « Étudiant en mécatronique qui aime apprendre… ») plutôt que de copier mot à mot. Les 6 tests sont passés, mais un modèle plus petit pourrait être plus erratique.
- **Profils non supprimables** : ni tool ni endpoint DELETE — volontaire pour cette expérimentation (PUT suffit pour corriger un champ).
- **Un seul profil par user** : structure fixée à `{"name", "description"}` — pas de liste de faits, pas d'historique de révisions (le brief interdit explicitement niveau/progression/mastery/objectifs dans cette version).
- **Verrou global du store** : un RLock sérialise tous les accès store (nécessaire avec une connexion sqlite partagée). Suffisant pour un dashboard mono-serveur ; pour du multi-process, un store Postgres serait requis.
- **Mise à jour par fusion** : un update partiel fusionne avec l'existant ; si l'agent réécrit un champ, seule la dernière version subsiste (pas d'accumulation).
- **Étapes futures prévues par le brief** (non implémentées volontairement) : Learning Profile, progression, mastery, quiz, révision espacée — cette version valide uniquement le socle `user_id → store → profil` cross-thread.

---

# V3 — MemoryFacts structurés + Context Engineering

## 10. Objectif V3

Évoluer la mémoire « un profil par user » (v2) en **faits indépendants categorisés** (MemoryFacts), et introduire un **Context Builder** qui sélectionne la mémoire pertinente et assemble un prompt dynamique par appel. Contrainte ferme : **ne rien casser** (checkpointer, threads, isolation, profil v2, frontend).

## 11. Fichiers créés / modifiés V3

**Créés :**
- `backend/app/context/__init__.py` — package Context Engineering
- `backend/app/context/builder.py` — `build_context(user_id, thread_id, query, subject=None, topic=None)` : orchestration + observabilité
- `backend/app/context/user_context.py` — sélection mémoire + formatage par catégories (Name/Background/Interests/…)
- `backend/app/context/thread_context.py` — résumé thread **sans dupliquer l'historique** (géré par le checkpointer)
- `backend/app/context/prompt_builder.py` — `build_system_prompt()` : Core Prompt + USER CONTEXT assemblés

**Modifiés :**
- `backend/app/agent/memory.py` — MemoryFacts : `save_fact/list_facts/update_fact/delete_fact/search_facts` + dédup + `memory_overview_for_api` ; profil v2 conservé intact
- `backend/app/agent/tools.py` — 5 nouveaux tools + `get/update_user_profile` conservés
- `backend/app/agent/prompts.py` — Core Prompt v3 (règles §1–§10, contre-exemples explicites)
- `backend/app/agent/middleware.py` — `MEMORY_TOOL_NAMES` étendu à 7 tools ; `wrap_model_call` reconstruit le prompt via le Context Builder
- `backend/app/api/schemas.py` — `MemoryFactOut/MemoryOverviewOut/MemoryFactCreate/MemoryFactUpdate`
- `backend/app/api/users.py` — 6 nouveaux endpoints memory
- `frontend/src/types/agent.ts` — `MemoryFact`, `MemoryOverview`, catégories, `TOOL_NAMES` (10)
- `frontend/src/api/memory.ts` — `getMemoryOverview/createMemoryFact/updateMemoryFact/deleteMemoryFact`
- `frontend/src/hooks/useMemory.ts` — `overview`, `addFact/editFact/removeFact`
- `frontend/src/components/memory/LongTermMemoryCard.tsx` — refonte complète (catégories, CRUD, filtre, Raw Memory)
- `frontend/src/pages/MemoryPage.tsx` — câblage nouvelle carte
- `frontend/src/components/tools/ToolStatusPanel.tsx` + `frontend/src/pages/LogsPage.tsx` — nouveaux events

## 12. Schéma de mémoire v3 (MemoryFact)

```json
{
  "id": "52a53c61795a",            // uuid4 court, identifiant unique
  "category": "interest",           // identity|background|personality|preference|interest
  "content": "Adore la robotique", // un fait = une phrase courte
  "source": "user",                // user (v3) ; inferred/system/teacher réservés
  "confidence": 1.0,               // 1.0 = déclaré explicitement
  "created_at": "2026-09-09T17:53:36+00:00",
  "updated_at": "2026-09-09T17:53:36+00:00"
}
```

- Stockage : même `SqliteStore` (`long_term_memory.db`), namespace `("users","profile",user_id)`, **clé `"facts"`** (liste) à côté de la clé `"profile"` (v2, intacte).
- Chaque fait est **indépendant** : jamais fusionnés en une description ; coexistence par catégorie.
- Profil v2 (`name`/`description`) inchangé et toujours fonctionnel (tools + endpoints + frontend).

## 13. Mécanique de déduplication

Avant chaque insert, `save_fact` compare le nouveau contenu aux faits existants **de la même catégorie** :

1. **Normalisation** : minuscules, sans accents/ponctuation, stop-words fr/en retirés, mots triés.
2. **Similarité = max de deux vues** :
   - *overlap coefficient* des mots signifiants (≥5 chars) : `|A∩B| / min(|A|,|B|)` — détecte « Aime la robotique » ≈ « S'intéresse à la robotique » (score 1.0) ;
   - *SequenceMatcher* sur chaîne triée — reformulations proches.
3. **Seuil ≥ 0.72** → l'fait existant est mis à jour (`content`, `updated_at`, `confidence = max`, `source`) + events `MEMORY_DEDUP` + `MEMORY_UPDATE`. Sinon création + `MEMORY_WRITE`.

Conservateur par design : « Préfère les exemples concrets » vs « Préfère les exemples pratiques » (0.67) ne dédup pas — préférences distinctes.

## 14. Tools mémoire (7)

| Tool | Signature | Rôle |
|---|---|---|
| `get_user_profile` | `(user_id)` | profil v2 (compat) |
| `update_user_profile` | `(user_id, name?, description?)` | profil v2 (compat) |
| `get_user_memory` | `(user_id, category?)` | liste les faits (filtrable) |
| `save_user_memory` | `(user_id, category, content, confidence?)` | 1 fait, dédup auto |
| `update_user_memory` | `(user_id, memory_id, content?, category?)` | modifie UN fait par id |
| `delete_user_memory` | `(user_id, memory_id)` | supprime UN fait par id |
| `search_user_memory` | `(user_id, query, category?)` | pertinence par mots-clé |

Sécurité inchangée : le middleware **force le user_id de la config** dans les args des 7 tools — le LLM ne peut jamais lire/écrire la mémoire d'un autre utilisateur.

## 15. Context Builder (séparation des responsabilités)

```
State (checkpointer)      = conversation actuelle (messages, déjà injectés par LangGraph)
Long-Term Store           = mémoire persistante (profil + facts)
Context Builder           = SÉLECTIONNE (search par pertinence + complément récent, quota 12)
Prompt Builder            = ASSEMBLE (Core Prompt + USER CONTEXT + contexte thread)
LLM                       = raisonne
```

- `build_context(user_id, thread_id, query, subject=None, topic=None)` retourne `{"user", "thread", "subject" (None), "learning" (None, réservé), "relevant_memories", "stats"}`.
- Le USER CONTEXT n'est PAS une copie de l'historique : l'historique reste géré par le checkpointer, le thread context n'ajoute que les métadonnées.
- Extraction restée **agent-driven** : le Core Prompt encode les règles (explicite uniquement, catégories, un fait par appel, interdiction questions/calculs/inférences comportementales) — pas de pipeline d'extraction parallèle.

## 16. Dynamic Prompt

`wrap_model_call` (middleware) reconstruit le system prompt à **chaque appel LLM** :

```
CORE PROMPT (stable, §règles 1–10)
  + ## USER CONTEXT (faits sélectionnés par le builder, groupés par catégorie)
  + ## Contexte courant (user_id/thread_id)
```

Fallback : si le builder échoue, `CONTEXT_BUILD_ERROR` est loggé et le Core Prompt seul est utilisé — l'appel LLM ne casse jamais.

## 17. Nouveaux événements de log

Mémoire : `MEMORY_READ`, `MEMORY_WRITE`, `MEMORY_UPDATE`, `MEMORY_DELETE`, `MEMORY_SEARCH`, `MEMORY_DEDUP`, `MEMORY_SKIP` (réservé contenu non durable), + variantes `_ERROR`.
Contexte : `CONTEXT_BUILD_START/END`, `PROMPT_BUILD`.
Observabilité : `USER_MEMORY_SELECTED`, `THREAD_CONTEXT_SELECTED`, `MEMORIES_USED` (dans les extras CONTEXT_BUILD_END), `CONTEXT_SIZE`, `PROMPT_CONTEXT_BUILT` (= PROMPT_BUILD).
Aucun secret jamais loggé (`log_safe` 80 chars).

## 18. Frontend /memory v3

- **Catégories en bullets** : Identity (nom v2 + description), Background, Personality, Preferences, Interests — avec compteurs et **filtres par catégorie**.
- **CRUD complet** : refresh, édition inline d'un fait, suppression ciblée par fait (icône), ajout manuel (sélecteur catégorie + contenu), édition du profil v2 conservée.
- **Raw Memory inspector** : bouton `Raw` — affiche les objets exacts du store (JSON brut avec id/source/confidence).
- Chat : la trace d'exécution affiche désormais `context build → memories selected → context built → prompt built` avant les tools.

## 19. Tests V3 — 16/16 + 4/4 PASS (NE PAS SIMULER respecté)

Tous les tests passent par l'API réelle (backend démarré, LLM cloud réel).

| Test | Scénario | Résultat |
|---|---|---|
| **A** | 1 message, 4 infos perso → 4 faits en 4 catégories, pas de fusion | **PASS** (4 faits : identity/background/interest/preference) |
| **B** | Nouveau thread « Que sais-tu de moi ? » → mémoire cross-thread complète | **PASS** (nom + mécatronique + robotique + préférence) |
| **C** | Kill backend → relance → faits intacts + utilisables dans un nouveau thread | **PASS 4/4** (3 faits conservés, réponse correcte post-restart) |
| **D** | User Beta « Que sais-tu de moi ? » → aucune fuite, 0 fait | **PASS** (« je ne sais rien de vous ») |
| **E** | « je m'intéresse à la robotique » après « j'adore la robotique » → 1 fait, pas 2 | **PASS** (MEMORY_DEDUP, même id) |
| **F** | DELETE du fait robotique → les 3 autres restent | **PASS** (restants: 3) |
| **G** | « Quelle heure est-il ? » + explication liste Python → 0 nouveau fait | **PASS** (3 avant = 3 après) |
| **H** | « Explique-moi quelque chose » → logs montrent exactement ce qui a été injecté | **PASS** (CONTEXT_BUILD/USER_MEMORY_SELECTED/PROMPT_BUILD × chaque appel, chars comptés) |

Vérification unitaire préalable (6/6) : imports + similarité/dédup + CRUD faits + rétro-compat profil v2 + context builder + schémas API.

### 19.1 Vérification exhaustive des 7 tools mémoire (2 niveaux)

**Niveau 1 — couche @tool directe (14/14 PASS)** : chaque tool invoqué comme le ToolNode le fait (`.invoke({...})`), sans LLM :
`get_user_profile` (vide → message), `update_user_profile` (+ relecture), `save_user_memory` ×3 catégories, `get_user_memory` (liste + filtre), `search_user_memory` (hit + zéro bruit), `update_user_memory` (cible par id, autres intacts), `delete_user_memory` (cible partie, autres restants) + **validations d'erreurs** (catégorie inconnue rejetée, id introuvable rejeté — le LLM peut se tromper, le tool refuse proprement).

**Niveau 2 — LLM réel via API (18/18 PASS)** : chaque tool **appelé par le modèle lui-même** sur instruction naturelle, vérifié dans les logs (TOOL_START) ET dans le store :
- `get_user_profile` : « lis mon profil » → tool appelé ✓
- `update_user_profile` : « enregistre que je m'appelle Ibrahima Diop » → tool appelé + profil écrit ✓
- `save_user_memory` : « je m'intéresse à la programmation embarquée » → fait créé ✓
- `update_user_memory` : « remplace ce souvenir par … (id) » → contenu mis à jour ✓
- `search_user_memory` : « fais une recherche sur 'programmation' » → tool appelé ✓
- `delete_user_memory` : « supprime uniquement le fait (id) » → fait supprimé **et profil v2 intact** ✓
- `get_user_memory` : « liste ta mémoire » → tool appelé ✓

Observation : le LLM écrit les faits à la 3e personne (ex. « Est en 2e année d'études ») conformément au prompt — format cohérent pour la relecture contextuelle.

**Données réelles stockées** (user « V3 Test Alpha », thread T1) :
```json
[{"id":"...","category":"identity","content":"S'appelle Alpha V3","source":"user","confidence":1.0,...},
 {"id":"...","category":"background","content":"Étudiant en mécatronique","source":"user","confidence":1.0,...},
 {"id":"...","category":"preference","content":"Préfère apprendre avec des exemples concrets plutôt que de la théorie","source":"user","confidence":1.0,...}]
```
Réponse B (extrait) : « Tu t'appelles Alpha V3. Tu es étudiant en mécatronique. Tu es passionné par la robotique. Tu préfères apprendre via des exemples concrets. »

## 20. Limites V3 + recommandations V3 Learning Profile

**Limites :**
- Dédup lexicale (pas sémantique) : paraphrases très différentes peuvent créer un quasi-doublon ; un embedding (ex. `nomic-embed-text` local) améliorerait `search`/dédup sans changer l'API.
- `search_facts` = scoring par mots-clé ; le store supporte `store.search(query=)` natif mais sans index sémantique configuré, le scoring custom reste plus prévisible.
- Extraction agent-driven : la qualité dépend du modèle ; Gemma 31B a passé tous les tests (A/E/G), un modèle plus petit pourrait sur-enregistrer.
- Quota mémoire par appel fixe (12 faits) — suffisant pour des profils tutoriels, à rendre adaptatif si les faits dépassent la centaine.
- Le RLock global store persiste (mono-serveur).

**Recommandations Learning Profile (V4, interfaces déjà préparées) :**
1. **Ajouter la catégorie `learning`** : trivial (une ligne dans `FACT_CATEGORIES`), les 5 tools et le builder la prennent en charge automatiquement.
2. **Champs `subject`/`topic` de `build_context` déjà câblés** : un futur Subject Router n'aura qu'à remplir ces clés — le Core Prompt et le prompt_builder les attendent déjà.
3. **Clé `"learning"` réservée** dans le contexte : le Learning Profile (mastery/score/progression) pourra s'y injecter sans toucher au reste.
4. **`source: "teacher"` et `inferred`** déjà dans `FACT_SOURCES` : la détection automatique de maîtrise pourra écrire des faits `confidence < 1.0` différenciés des déclarations utilisateur.
5. **MEMORY_SKIP** prévu dans le prompt/logs : un futur validateur d'extraction pourra logger pourquoi une info n'a PAS été mémorisée.
6. Basé sur les faits `preference` existants (ex. « exemples concrets »), un moteur de recommandation pédagogique peut déjà personnaliser sans nouveau socle technique.

---

# V4 — Subject Registry & Context Engineering

## 21. Objectif V4

Passer de « tuteur Python à mémoire » à **moteur pédagogique central** : un seul agent dont le contexte est construit dynamiquement à partir de plusieurs sources (Router → Subject Config → Knowledge → Tools → User Memory → Thread), au lieu d'un system prompt géant ou d'un agent par matière. **Ajouter une matière = 1 fichier YAML + des fichiers knowledge — zéro modification moteur.**

## 22. Architecture V4

```
Question user
  ▼
Subject Router (déterministe, sans LLM)                    app/context/router.py
  │ keywords/aliases/topics des SubjectConfigs + taxonomy
  │ → {subject, topic, confidence, status}
  ▼
Subject Registry (YAML-driven)                             app/subjects/
  │ definitions/*.yaml → SubjectConfig                     registry.py, schema.py
  │ taxonomy.py : matières détectables non-configurées
  ▼
Knowledge Retriever (fichiers .md par sections)             app/context/knowledge_retriever.py
  │ search_knowledge(subject, topic, query)
  │ → sections pertinentes SEULEMENT (jamais tout chargé)
  ▼
Tool Registry                                               app/subjects/tool_registry.py
  │ implémentés (10 réels) vs déclarés (communs/spécialisés)
  ▼
Context Builder (= SÉLECTION)                               app/context/builder.py
  │ router + subject + knowledge + tools + user memory + thread
  ▼
Prompt Builder (= ASSEMBLE)                                app/context/prompt_builder.py
  │ CORE TUTOR (générique) + MATIÈRE + KNOWLEDGE
  │ + NOTE DU SYSTÈME (fallbacks) + USER + THREAD
  ▼
Middleware wrap_model_call                                  app/agent/middleware.py
  │ prompt assemblé → modèle ; fallback Core si échec
```

**Hiérarchie Domaine → Matière → Topic** : `informatique/python/fonctions`, `sciences/biologie/membrane`.

## 23. Fichiers créés / modifiés V4

**Créés :**
| Fichier | Rôle |
|---|---|
| `app/subjects/__init__.py`, `schema.py` | SubjectConfig/TopicConfig — schéma standard, générique |
| `app/subjects/registry.py` | Chargement `definitions/*.yaml` (singleton thread-safe), lookup |
| `app/subjects/definitions/python.yaml` | 4 matières configurées : python, biology, mathematics, computer_networks |
| `app/subjects/taxonomy.py` | 8 matières détectables non-configurées (astrophysique, chimie, neural_networks…) — fallback unsupported |
| `app/subjects/tool_registry.py` | IMPLEMENTED_TOOLS (10) vs déclarés ; TOOLS_SELECTED |
| `app/knowledge/**` (9 .md) | informatique/python (4), reseaux (2), sciences/biologie (2), mathematics/algebre (1) — sections `## topic` |
| `app/context/router.py` | route_subject() — 5 statuts, normalisation accents NFD, frontières de mots |
| `app/context/knowledge_retriever.py` | search_knowledge() — scoring containment, stop-words FR, seuil 0.3 |
| `app/context/tool_context.py` | Wrapper builder → tool_registry |
| `app/api/subjects.py` | GET /api/subjects, /{id}, /{id}/topics, POST /preview/context |

**Modifiés :**
| Fichier | Changement |
|---|---|
| `app/agent/prompts.py` | Core Tutor **générique** (plus « spécialisé Python ») + règles matières/fallbacks |
| `app/context/builder.py` | V4 multi-sources + §39 (fill mémoire plafonné, seulement si search vide) |
| `app/context/prompt_builder.py` | Blocs MATIÈRE/NOTE DU SYSTÈME/KNOWLEDGE + routing |
| `app/context/__init__.py` | Exports build_context/build_system_prompt/route_subject |
| `app/agent/middleware.py` | wrap_model_call → pipeline V4 ; strip ## USER CONTEXT **et** ## MATIÈRE |
| `app/api/schemas.py` | SubjectOut/TopicOut/ContextPreviewRequest/Response (additif) |
| `app/main.py` | include subjects.router |
| `frontend/src/types/agent.ts` | SubjectInfo, RouterInfo, ContextPreview, KnowledgeItem… |
| `frontend/src/api/subjects.ts` | Client API subjects + preview |
| `frontend/src/components/memory/ContextInspectorCard.tsx` | Carte Current Subject + sections extensibles |
| `frontend/src/pages/MemoryPage.tsx` | Intégration ContextInspectorCard |
| `frontend/src/components/tools/ToolStatusPanel.tsx` | TRACE_EVENTS + : routing, knowledge, subject, tools |
| `frontend/src/pages/LogsPage.tsx` | EVENT_TONES : ROUTING_*, KNOWLEDGE_*, TOOLS_*, SUBJECT_* |

## 24. Schémas V4 documentés

**SubjectConfig (YAML → dataclass)** : `id, name, domain, description, teaching_style[], pedagogical_guidelines[], capabilities[], tools{common[], specialized[]}, knowledge{sources[]}, topics[], aliases[], model{provider, name}`.

**RouterResult** : `subject, topic, confidence, status, candidates[], subjects[]`.

**Knowledge search** : `{status: found|insufficient|unavailable, items: [{source, topic, content, relevance}], searched_sources}`.

**Context (build_context)** : `{router, subject, knowledge, tools, user, thread, learning: null, relevant_memories, stats}` — la clé `learning` reste réservée au Learning Profile (V5+).

## 25. Les 6 cas de fallback (§33/§34 — situations NORMALES, jamais erreurs)

| Cas | Statut router | Comportement observé |
|---|---|---|
| Matière configurée + knowledge | `supported` | Bloc MATIÈRE + CONNAISSANCES DU COURS injectés |
| Matière configurée, topic sans doc | `supported` + knowledge `insufficient` | NOTE « aucune connaissance trouvée → pas d'invention, recherche_web si pertinent » |
| Question ambiguë (réseaux) | `ambiguous` + candidates | NOTE « demande une clarification » — 2 candidats listés au LLM |
| Matière non-configurée (astrophysique) | `unsupported` | NOTE « tuteur général » — **vérifié en chat réel : le LLM annonce lui-même ne pas avoir de configuration** |
| Rien d'identifié | `unknown` | Core seul, tuteur général |
| Multi-domaines | `multi_domain` | NOTE clarification domaine |

**« Matière supportée ≠ Knowledge suffisante »** : test 5 prouve la distinction (python supported + knowledge insufficient, deux statuts indépendants).

## 26. Observabilité — nouveaux événements

| Événement | Émis par | Frontend |
|---|---|---|
| `ROUTING_START` / `ROUTING_END` | router | Trace (indigo/vert) + Logs |
| `SUBJECT_CONTEXT_SELECTED` | builder | Trace + Logs |
| `KNOWLEDGE_SEARCH` | retriever | Trace + Logs |
| `KNOWLEDGE_SELECTED` | builder (si items) | Trace (vert) + Logs |
| `TOOLS_SELECTED` | tool_registry | Trace + Logs |
| `SUBJECT_REGISTRY_LOADED` | registry (startup) | Logs (ambre) |
| `SUBJECT_REGISTRY_ERROR` | registry | Logs (rouge) |

`CONTEXT_BUILD_END` transporte en extra : subject, topic, routing_status, memory_items, knowledge_items, tools, context_size, user_memory_selected, thread_context_selected.

## 27. Qualité du contexte (§39 — mémoire minimale)

Nouvelle règle de sélection : search par pertinence ; **fill récent plafonné à 3 faits (1 identity/background + 2 récents) et seulement si la search n'a rien retourné**. Test qualité : user avec robotique/aéronautique/mécatronique + préférences → query « Explique les fonctions Python » → intérêts **absents** du prompt, préférences **présentes**. PASS.

## 28. Tests V4 — tous PASS (aucune simulation)

**Unitaires (sans LLM) : 20/20** — registry (4), router (7 : python/fonctions, biology/membrane, réseaux→ambiguous 2 candidats, astrophysique→unsupported, unknown, explicite→computer_networks, hint), knowledge (4 : return found 1.0, oop found, insufficient, unavailable), tools (2), prompt builder (3 : blocs présents, note unsupported, note ambiguous).

**Intégration (API réelle) : 19/19** — Tests 1–10 du brief + §39 :
1. Python fonctions → (python, fonctions, supported) + subject config + knowledge found + tools déclarés
2. Biologie membrane → (biology, membrane, supported) + cell.md trouvé
3. « les réseaux » → ambiguous [computer_networks, neural_networks] + note clarification dans le prompt
4. Astrophysique → unsupported + PAS de bloc MATIÈRE + note limite
5. Decorators/async → python supported + knowledge insufficient (distinction matière/connaissance)
6. Mémoire sélectionnée comme contexte (115 chars)
7. Thread context = thread courant uniquement
8. Cross-thread : user context identique, thread différent
9. Isolation A/B : facts de A absents de B
10. Contexte minimal : user vide + query neutre → memories_used = 0
§39. Intérêts non pertinents absents, préférences présentes

**Régression V3 : 5/5** — R1 chat LLM répond (prompt V4), R2 checkpointer intact (2 messages), R3 fallback unsupported en chat réel (le LLM dit lui-même ne pas avoir de configuration), R4 CRUD mémoire intact, R5 mémoire cross-thread accessible au LLM (« D'après vos informations, vous préférez les résumés courts »).

**Frontend : build tsc strict 0 erreur** (469 kB gzip 144 kB).

## 29. Compatibilité future (§46 — 16 critères)

- **Ajouter une matière** : 1 YAML + knowledge .md — router/registry/builder génériques, zéro `if subject ==` dans le moteur. Vérifié : computer_networks ajouté par config seule.
- **Learning Profile** : clé `"learning"` déjà dans le contexte (null), bloc LEARNING attendu par prompt_builder.
- **Learning Engine** : `learning_engine.decide(user_id, subject, topic, context)` s'intercale entre router et builder.
- **RAG externe** : remplacer `_available_sources`/scoring par embeddings — l'API `search_knowledge` ne change pas.
- **Multi-agents par domaine** : le router expose déjà domain + candidates ; un routeur LLM pourrait affiner l'ambiguous.
- **Tools spécialisés** : `execute_python` déclaré dans le YAML ; l'implémenter = l'ajouter à IMPLEMENTED_TOOLS, il apparaît dans toutes les matières qui le déclarent.
- **Multi-modèles** : `model{provider, name}` présent dans chaque SubjectConfig.
- **HITL routing** : `route_subject(query, hint_subject=...)` accepte déjà un hint explicite (utilisé par preview/context).

**Limites V4 connues :** routing lexical (pas sémantique — paraphrases non listées tombent en unknown → tuteur général, jamais de crash) ; knowledge = mots-clés (embedding = V5) ; les événements ROUTING_*/KNOWLEDGE_* se répètent à chaque hop LLM (post-tool) — bruit attendu, filtrable côté frontend.

## 30. V4.1 — Tools pédagogiques communs : implémentations RÉELLES

Le brief exigeait des vraies implémentations (pas des simulations). Trois tools ajoutés dans `app/agent/pedagogical_tools.py`, branchés sur la base knowledge réelle — chaque exercice/évaluation/indice est construit depuis le **contenu du cours**, jamais inventé :

| Tool | Mécanisme réel |
|---|---|
| `create_exercise(subject, topic)` | Récupère la section knowledge du topic → extrait les termes-clés (longueur × fréquence) → exercice structuré : question ouverte + critères de réussite (définition, termes, exemple) + renvoi vers evaluate_answer. Topic introuvable → liste les topics réels, pas d'invention. |
| `evaluate_answer(subject, topic, answer)` | Scoring déterministe : couverture des termes-clés du cours (70%) + richesse du vocabulaire (30%) → score %, verdict formatif, termes couverts/manquants, prochaine étape pédagogique (indice/encouragement/approfondissement). |
| `give_hint(subject, topic, level)` | Indices progressifs depuis le contenu : niveau 0 orientation (direction), niveau 1 précision (mécanisme), niveau 2 presque-solution (définition du cours). Croissants en contenu révélé. |

**Câblage** : `all_tools` = 3 + 7 mémoire + 3 pédagogiques = **13 tools**. `IMPLEMENTED_TOOLS` mis à jour ; les commons n'apparaissent plus « déclarés à venir » (seuls les spécialisés restent déclarés : execute_python, analyze_diagram, verify_solution…). Règles 11–14 ajoutées au Core Prompt (exercice via tool, évaluation après réponse, hint AVANT indice maison, pas d'invention hors base).

**Tests — tous PASS, aucune simulation :**
- **Directs (16/16)** : exercice construit depuis knowledge avec source citée ; topic inconnu → topics réels listés ; bonne réponse 76% / mauvaise 0% + advice give_hint ; 3 niveaux d'indices distincts et croissants (195/358/493 chars) ; générique sur biology/membrane ; registry 13 dispo, commons sortis des « déclarés », spécialisés conservés ; all_tools = 13.
- **LLM réel (3/3)** : « Donne-moi un exercice sur le return » → le tuteur **appelle create_exercise** et reformule l'exercice réel ; réponse de l'étudiant → **appelle evaluate_answer** ; « je bloque, donne-moi un indice » → **appelle give_hint** (après renforcement de la règle 13 : le tool d'abord, pas l'indice maison).
- **Frontend** : TOOL_NAMES 10 → 13, build tsc strict 0 erreur.

**Non-invention vérifiée** : chaque sortie cite sa source (`python/functions`, `biologie/cell`…) ; un topic absent de la base ne produit jamais d'exercice fabriqué — le tool retourne la liste des topics réels et le prompt interdit d'inventer.


## 31. V5 — Audit & Refactorisation : mécanismes natifs LangChain/LangGraph

**Mission** : distinguer les mécanismes officiels LangChain des composants métier, et câbler le projet sur les APIs natives. **Contrainte** : ne rien casser (SqliteSaver, SqliteStore, user_id, thread_id, MemoryFacts, mémoire cross-thread, isolation utilisateurs, tools pédagogiques, SSE, EventBus, logs, frontend, API).

### 31.1. APIs LangChain/LangGraph natives utilisées (audit final)

| API | Version | Pourquoi | Référence documentaire |
|---|---|---|---|
| `create_agent(...)` | langchain 1.3.15 | Assemblage standard de l'agent (model, tools, system_prompt, checkpointer, store, state_schema, context_schema, middleware) | docs.langchain.com/oss/python/langchain/agents |
| `context_schema=AgentContext` (paramètre de create_agent) | langchain 1.3.15 | Déclare le schéma du Runtime Context — user_id/thread_id voyagent dans `context=` (§4), plus dans le configurable | docs.langchain.com/oss/python/langchain/runtime |
| `agent.invoke(input, config=..., context=AgentContext(...))` | langgraph 1.2.11 | Injection du Runtime Context à chaque appel LLM — le middleware y lit user_id via `request.runtime.context` | docs.langchain.com/oss/python/langchain/runtime |
| `@dynamic_prompt` (decorator → AgentMiddleware) | langchain 1.3.15 | **Remplace** le wrap_model_call custom qui écrasait le prompt : le prompt dynamique devient le mécanisme officiel (§8/§34) | docs.langchain.com/oss/python/langchain/runtime (dynamic prompt) |
| `ModelRequest` (request.runtime.context / .state) | langchain 1.3.15 | Signature officielle du dynamic prompt ; le métier lit le contexte du runtime, pas get_config() | docs.langchain.com/oss/python/langchain/runtime |
| `SqliteSaver` (langgraph-checkpoint-sqlite 3.1.1) | langgraph 1.2.11 | Checkpointer thread state — conversation continuity, get_state, get_state_history (§7) | docs.langchain.com/oss/python/langgraph/persistence |
| `SqliteStore` (BaseStore) | langgraph 1.2.11 | Store longue durée — User Memory cross-thread, namespace user (§6) | docs.langchain.com/oss/python/langgraph/persistence (stores) |
| `AgentMiddleware.wrap_tool_call` | langchain 1.3.15 | Observabilité TOOL_* + forçage user_id (sécurité mémoire, §47) via request.runtime.context | docs.langchain.com/oss/python/langchain/middleware |
| Pydantic v2 (`BaseModel`, `Field`, `Literal`) | pydantic 2.12.5 | RoutingResult / BuiltContext / KnowledgeSearchResult / ResolvedTools — sorties structurées validées (§14/§30) | docs.langchain.com/oss/python/langchain/structured-output |

### 31.2. Composants métier (custom) — pourquoi ils restent

| Composant | Rôle métier | Pourquoi ce n'est pas un mécanisme LangChain |
|---|---|---|
| `subjects/registry.py` | Subject Registry YAML (singleton) | LangChain n'a pas de concept de « matière configurable » ; c'est le Domain du projet |
| `context/router.py` | Classification subject/topic/status → RoutingResult | Le routing métier (taxonomy, alias, anti-collision) est du Domain Knowledge, pas une API LangChain |
| `context/knowledge_retriever.py` | Récupération knowledge par topic (§26) | Base knowledge locale = métier ; structure prête pour un remplacement embeddings (V6) |
| `context/builder.py` | Assemblage BuiltContext (sélection, priorisation, budget §30/§31) | Le Context Builder orchestre les SOURCES de contexte — le mécanisme LangChain est en amont (dynamic_prompt) et aval (ModelRequest) |
| `context/prompt_builder.py` | Présentation du BuiltContext → prompt (§35) | Pure fonction de mise en forme — appelée PAR le dynamic_prompt natif |
| `subjects/tool_registry.py` | resolve_tools : croise déclaré × implémenté (§28/§39) | Filtrage métier ; les tools restent des @tool LangChain standards |
| `agent/memory.py` | Memory Facts sur SqliteStore (CRUD + search) | Namespace/format métier sur le Store officiel |
| `logging/events.py` + SSE | EventBus observabilité | Infrastructure projet (temps réel frontend) |

**Principe appliqué** : LangChain transporte et expose (`context=`, `request.runtime.context`, `dynamic_prompt`, `wrap_tool_call`) ; le métier décide (routing, sélection, priorisation).

### 31.3. Audit des hardcodes (§58)

- **Aucun** `if subject == ...` dans le moteur (grep exhaustif) — l'architecture V4 avait déjà éliminé le hardcode matière.
- 4 heuristiques locales légitimes (classe C — heuristiques de composant, documentées, testables, sans impact routing) : `_STOP_WORDS` (memory.py — dédup mémoire), `_EVAL_STOP_WORDS` (pedagogical_tools.py — scoring évaluation), `_KN_STOP_WORDS` (knowledge_retriever.py — scoring pertinence), listes taxonomy/alias (`subjects/taxonomy.py` — **données de configuration**, pas du code : ajouter une matière = 1 YAML, le taxonomy s'applique à tous).
- Décision : **conservées** — ce sont des heuristiques de composant local, pas du routing de matière.

### 31.4. Flux de contexte V5 (§72 appliqué)

```
USER MESSAGE (thread t, user u)
   │
   ├─ runner.run_agent_stream : agent.invoke(input, config={thread_id}, context=AgentContext(u, t))
   │      └─ thread_id reste dans configurable (checkpointer §7) ; user_id VIA le runtime
   │
   ├─ [@dynamic_prompt natif] request.runtime.context.user_id → build_context()
   │      ├─ router.route_subject()          → RoutingResult (pydantic §14)
   │      ├─ registry.get_subject()          → SubjectConfig (YAML §12)
   │      ├─ knowledge_retriever.search()    → KnowledgeSearchResult (§26)
   │      ├─ tool_registry.resolve_tools()   → ResolvedTools {available, unavailable} (§28/§39)
   │      ├─ memory (SqliteStore, search)    → facts pertinents (§31 : search d'abord, fill=personnalisation)
   │      └─ thread_context (léger §32)     → métadonnées
   │      → BuiltContext (pydantic §30)
   │      → prompt_builder.build_system_prompt() → prompt (§35, §36 : aucune VALEUR d'ID)
   │      → request.override(system_message=...)  [mécanisme officiel]
   │      └─ fallback §37 : exception → log CONTEXT_BUILD_ERROR → CORE_PROMPT seul (jamais de crash)
   │
   ├─ [wrap_tool_call] TOOL_START/END/ERROR + forçage user_id des tools mémoire
   │      (request.runtime.context.user_id remplace get_config() — isolation §47 testée LLM réel)
   │
   └─ SqliteSaver checkpoint → SqliteStore memory cross-thread
```

### 31.5. Tests V5 — tous PASS, aucune simulation

**Architecture (`backend/tests/test_v5_architecture.py` — 30/30)** :
- §54 routing structuré : RoutingResult pydantic validé, Literal rejeté si invalide, confidence bornée
- §51 ambiguïté réseaux : candidates=[computer_networks, neural_networks] ; §50 astrophysique unsupported ; §17 unknown sans invention
- §49 **ajout de matière par config seule** : astronomy.yaml + 1 .md → découverte registry/routing/knowledge SANS toucher builder/graph/runner/middleware (test effectué, fichiers supprimés après vérification)
- §53 tool inexistant : execute_python déclaré → unavailable + log, jamais exposé
- §30 BuiltContext pydantic + stats budget ; §48 configs non mélangées (python vs biology)
- §45 sélection mémoire : interests topiques absents (search vide → fill = preferences/identity seulement, 66 chars)
- §55 dynamic prompt natif : MATIÈRE + USER CONTEXT (5102 chars), nouveau MemoryFact visible à l'appel suivant
- §56 fallback : sans user_id → CORE seul ; builder en erreur → CONTEXT_BUILD_ERROR → CORE (testé avec un VRAI ModelRequest.override)
- §36 aucune valeur d'ID technique dans le prompt ; §4 AgentContext câblé graph/runner (inspect.getsource)

**Intégration serveur (`backend/tests/test_v5_integration.py` — 10/10, LLM réel)** :
- chat LLM avec Runtime Context + dynamic prompt natif ; checkpointer intact (messages persistés)
- mémoire cross-thread (thread 2 répond la préférence enregistrée au thread 1) ; fallback unsupported honnête
- isolation A/B via preview ; **forçage user_id via runtime context vérifié LLM réel** (B voit Bruno, pas la mémoire de A ; A sauvegarde via tool save_user_memory → catégories ['interest','preference'])
- create_exercise appelé par le LLM ; 11+ événements observabilité présents (ROUTING_*, CONTEXT_BUILD_*, PROMPT_BUILD, TOOL_*, RUN_*, CHECKPOINT_SAVED) ; preview BuiltContext sérialisé identique sur les 2 routes

**Régression** : suite mémoire LLM (isolation + save via tool) PASS ; frontend `npm run build` (tsc strict) 0 erreur.

### 31.6. Fichiers modifiés / créés

**Créés** :
- `backend/app/context/schemas.py` — AgentContext (runtime), RoutingResult, KnowledgeResult, KnowledgeSearchResult, ResolvedTools, ContextPriority, Subject/User/ThreadContextInfo, ContextStats, BuiltContext
- `backend/app/api/context.py` — POST /api/context/preview (§44, alias canonique ; l'ancienne route reste pour le frontend)
- `backend/tests/test_v5_architecture.py`, `backend/tests/test_v5_integration.py`

**Modifiés** :
- `backend/app/context/router.py` — retourne RoutingResult pydantic (logique V4 inchangée)
- `backend/app/context/builder.py` — retourne BuiltContext ; fill mémoire = personnalisation uniquement (§45) ; KNOWLEDGE_UNAVAILABLE loggé (§38)
- `backend/app/context/prompt_builder.py` — présentation pure (§35), consomme BuiltContext
- `backend/app/agent/middleware.py` — @dynamic_prompt natif + wrap_tool_call (rôle réduit §60) ; user_id depuis request.runtime.context (plus get_config)
- `backend/app/agent/graph.py` — context_schema=AgentContext ; stack middleware build_middleware_stack()
- `backend/app/agent/runner.py` — context=AgentContext(...) à chaque invoke
- `backend/app/subjects/tool_registry.py` — resolve_tools (§28/§39) + compat get_tools_for_subject
- `backend/app/api/subjects.py` + `main.py` — preview via BuiltContext.model_dump(), route context
- `frontend/src/types/agent.ts` — ToolsContext = {available, declared, unavailable}
- `frontend/src/components/memory/ContextInspectorCard.tsx` — affichage unavailable (§39)

### 31.7. Régressions confirmées non-cassées

SqliteSaver (checkpoints, get_state, history) ; SqliteStore (MemoryFacts CRUD+search) ; user_id/thread_id (transportés runtime + configurable compat) ; mémoire cross-thread ; isolation utilisateurs (LLM réel) ; 13 tools pédagogiques/mémoire (create_exercise appelé par le LLM en intégration) ; SSE/EventBus (11+ événements) ; logs ; frontend (build 0 erreur, preview OK) ; API (routes existantes + alias §44, réponses identiques).

### 31.8. Non implémenté (réservé)

Learning Profile (clé `learning` dans BuiltContext, null) ; RAG embeddings ; documents utilisateur ; multi-agents ; HITL ; tools spécialisés par matière (execute_python : déclaré, détecté unavailable, loggé §39).

## 32. V6 — Learning Profile : mémoire pédagogique persistante

**Mission** : introduire un Learning Profile persistant (« où en est l'étudiant ? »), distinct de User Memory (« qui est-il ? ») et du Thread State (« que se passe-t-il maintenant ? »), intégré à l'architecture V5 sans refonte (source n°7 du Context Builder → `BuiltContext.learning`).

### 32.1. Architecture

Trois mémoires strictement séparées, transportées par les mécanismes natifs V5 inchangés :

```
USER MESSAGE (thread t, user u)
   ├─ User Memory    ("users","profile",u)  SqliteStore  → qui est l'étudiant ?
   ├─ Learning Profile ("users","learning",u) SqliteStore → où en est-il ?   [NOUVEAU V6]
   └─ Thread State   (checkpointer thread t) SqliteSaver  → que se passe-t-il ?
   │
   └─ CONTEXT BUILDER (source 7 : get_learning_context — SÉLECTION PERTINENTE §25)
        → BuiltContext.learning (LearningContextInfo)
        → @dynamic_prompt natif (inchangé V5) → bloc ## LEARNING du prompt
        → LLM
```

Aucun deuxième Context Builder : le Learning Profile est une **source supplémentaire** du builder existant. Runtime Context, AgentContext, SqliteSaver, SqliteStore, @dynamic_prompt, Subject Registry, Router, Knowledge Retriever, Tool Registry, MemoryFacts, SSE, EventBus, logs, API V5 : **inchangés ou étendus, jamais modifiés structurellement**.

### 32.2. Data model (`app/learning/schemas.py`)

| Schéma | Champs | Rôle |
|---|---|---|
| `LearningProfile` | user_id, subjects: dict[str, SubjectLearningState], goals: list[LearningGoal], updated_at | Profil complet — AUCUN message de conversation (§34) |
| `SubjectLearningState` | mastery (agrégat pondéré), topics: dict[str, TopicLearningState] | Progression par matière (§16) |
| `TopicLearningState` | mastery, attempts, strengths, weak_points, last_assessed_at, confidence | État par topic — strengths/weak liés au topic, pas au user global (§30) |
| `LearningObservation` | subject, topic, type (exercise/quiz/assessment/teacher_feedback), score, strengths, weak_points, confidence, created_at | Observation SIGNIFICATIVE (§11-§12) — jamais créée par un message ordinaire |
| `LearningGoal` | id, subject, topic, description, status (active/completed/paused), created_at | Objectifs séparés de la maîtrise (§29) |
| `LearningContextInfo` | status (active/not_started/unavailable), subject, topic, mastery, attempts, strengths, weak_points, confidence, subject_mastery, goal | Sélection PERTINENTE exposée à BuiltContext.learning (§24) |

**Mastery n'est pas une vérité absolue (§9)** : c'est une estimation avec confidence — `mastery=0.63, confidence=0.72` se lit « estimation 63 %, confiance 72 % ».

### 32.3. Persistence (`app/learning/learning_profile.py`)

Même SqliteStore que User Memory (aucune nouvelle technologie, §5 Option A), namespace distinct (§6) :

| Donnée | Namespace | Clé | Contenu |
|---|---|---|---|
| Profil | ("users","learning",user_id) | "profile" | LearningProfile.model_dump() |
| Historique observations (§33) | ("users","learning",user_id) | "observations" | 50 dernières LearningObservation (FIFO, jamais écrasées) |
| Séquence goals | ("users","learning",user_id) | "goals_seq" | compteur monotone |

Séparation stricte avec User Memory («users","profile",user_id). Cross-thread par construction : le namespace ne contient JAMAIS thread_id (§4/§5).

**Profile Updater (§14)** — `update_profile_from_observation(user_id, observation)` :
1. charge (ou crée §27) le profil ; 2. valide subject/topic contre le Subject Registry (§18 — « pythonn » rejeté, pas de création silencieuse) ; 3. journalise LEARNING_OBSERVATION_RECORDED ; 4. historise l'observation (§33) ; 5. intègre (formule ci-dessous) ; 6. sauvegarde + LEARNING_PROFILE_UPDATE.

**Formule d'évolution (§15) — simple, déterministe, testée** :
```
w = OBSERVATION_WEIGHT (0.3) × source_weight × observation.confidence
source_weight : assessment/teacher_feedback = 1.0 ; exercise/quiz = 0.8 (§10 : les observations ne se valent pas)
new_mastery = old × (1−w) + score × w        (première observation : mastery = score)
confidence = 0.95 × attempts / (attempts + 3)  (asymptote : 1 obs→0.24, 10→0.73)
subject.mastery = moyenne des topics pondérée par attempts
```
Moyenne mobile exponentielle : l'estimation n'est jamais écrasée, un accident n'efface pas un profil solide, convergence en quelques observations. Aucun ML (§15). Vérifiée : (0.40 puis 0.70, exercise w=0.24) → 0.472 exactement.

**Résolution topic Registry (fix integration)** — `resolve_registry_topic(subject, topic, source)` : les tools pédagogiques travaillent en topics de SECTION knowledge (ex: `_intro` de functions.md) ; le profil indexe les topics du REGISTRY. Résolution : topic déjà valide → tel quel ; source `…/functions` → `functions` ; containment ; sinon **rejet** (§18, jamais de topic inventé).

### 32.4. Tools (§19-§23) — 4 tools, user_id forcé par middleware

| Tool | Signature | Sécurité |
|---|---|---|
| `get_learning_profile` | (user_id) → profil structuré / message not_started | §23 : user_id remplacé par le user_id du Runtime Context dans wrap_tool_call (LEARNING_TOOL_NAMES, même mécanisme que MEMORY_TOOL_NAMES) |
| `get_learning_topic` | (user_id, subject, topic) → état du topic (§21) | idem |
| `record_learning_observation` | (user_id, subject, topic, observation_type, score, strengths, weak_points, confidence) → validation pydantic + Registry (§18) puis update | idem |
| `update_learning_goal` | (user_id, action create/update, …) → goals (§29) | idem |

**Auto-observation déterministe (§13 appliqué)** : `evaluate_answer` enregistre LUI-MÊME l'observation après chaque vraie évaluation (pipeline natif Exercise → Evaluation → LearningObservation → Profile, topic résolu Registry, échec non bloquant §26). Le LLM garde `record_learning_observation` pour teacher_feedback/quiz — mais la progression ne dépend PLUS du bon-vouloir du modèle. Règle 15 du Core Prompt : obligatoire après evaluate_answer, JAMAIS pour un message ordinaire (§11).

**Logs (§37)** : LEARNING_PROFILE_READ/WRITE/UPDATE, LEARNING_OBSERVATION_RECORDED, LEARNING_GOAL_CREATED/UPDATED, LEARNING_CONTEXT_SELECTED — tous avec user_id/thread_id/subject/topic/operation, via l'EventBus existant (SSE + agent.log, aucun secret).

### 32.5. Context — du profil au Dynamic Prompt

`get_learning_context(user_id, subject, topic)` (§41 — interface stable pour le Learning Engine V7) sélectionne :
- topic routé + présent dans le profil → état réel (mastery, attempts, strengths, weak_points) ;
- topic Registry jamais travaillé → état minimal actif (mastery null, attempts 0 — §28, pas une erreur) ;
- sujet sans topic → topic le moins maîtrisé + mastery sujet (§25 : utile pédagogiquement) ;
- pas de sujet routé / pas de profil → not_started (§26 — le tuteur fonctionne normalement) ;
- erreur de lecture → unavailable (fallback silencieux, jamais de crash).

Le builder (source 7) injecte `BuiltContext.learning = LearningContextInfo.model_dump()` + LEARNING_CONTEXT_SELECTED (§38) + `learning_items` dans CONTEXT_BUILD_END. Le Prompt Builder (présentation pure, §35) rend le bloc :

```
## LEARNING (progression de l'étudiant sur ce topic)
Topic : python / fonctions
Mastery : 47% (estimation — confiance 38%)
Attempts : 2
Weak points : return vs print
Dernière évaluation : 2026-09-11
Adapte ton enseignement à cette progression...
```

Pour « Je veux continuer les fonctions Python » : Python/fonctions SEULEMENT — jamais la biologie ni tous les goals (§25, test §48 PASS).

### 32.6. Tests

**Architecture (`backend/tests/test_v6_learning.py`) — 35/35 PASS** :
- A nouveau profil → not_started (pas une erreur) ; B première observation crée le profil (mastery=score, weak/strength stockés §30) ; C formule exacte (0.40+0.70→0.472, attempts 2, confidence 0.38) ; D autre topic n'y touche pas ; E autre matière n'y touche pas ; F cross-thread (thread B lit thread A) ; G cross-user zéro fuite (A garde sa mastery, nouveau user → null) ; H persistance Store (relecture exacte) ; I BuiltContext.learning actif + bloc LEARNING + weak_points dans le prompt ; J nouvel étudiant → contexte et prompt complets (§26).
- §46 non-mélange (python 0.30 / biology 0.60 / mathematics 0.90 distincts) ; §47 LEARNING_OBSERVATION_RECORDED AVANT LEARNING_PROFILE_UPDATE (ordre des logs) ; §48 « Je ne comprends pas return » → python prioritised, biologie absente du prompt.
- Critères §51 : aucun champ messages (§34), pythonn + topic inconnu rejetés (§18), goals créés/complétés (§29), historique [0.4, 0.7] conservé (§33), état minimal topic Registry (§28), round-trip pydantic, namespace distinct (§5/§6), PAS de Learning Engine (§40), tools enregistrés (24 total).

**Intégration serveur (`backend/tests/test_v6_integration.py`) — 6/11, statut honnête** :
PASS : exercice créé (workflow règle 17 respecté : question puis attente), évaluation de réponse réussie, nouvel étudiant discute normalement (profil not_started via API), isolation utilisateurs API, événements LEARNING_* dans les logs (SSE/EventBus).
ÉCHECS au dernier run (IT2/3/7/8 : LLM n'a pas enregistré) : **cause identifiée = serveur obsolète**. Le run de tests a frappé un process uvicorn orphelin (port 8001) exécutant le code d'AVANT le fix `resolve_registry_topic` (preuve : log `Observation rejetée (Registry) | Topic '_intro' inconnu`) ; les restarts job_kill ne tuaient pas l'enfant uvicorn. Le fix est vérifié unitairement (`resolve_registry_topic('python','_intro','informatique/python/functions') → 'functions'`) et le process orphelin a été tué, le port libéré — mais le run LLM complet avec le fix n'a pas été re-exécuté avant la rédaction de ce rapport. À re-run : `python -m uvicorn app.main:app --port 8001` puis `python -X utf8 tests\test_v6_integration.py` (attendu : LEARNING_OBSERVATION_RECORDED + profil actif via l'auto-observation d'evaluate_answer).

**Régression frontend** : build tsc strict 0 erreur.

### 32.7. Structure réelle du projet (§49)

```
project/
├── backend/
│   ├── app/
│   │   ├── agent/                       # couche agent LangChain
│   │   │   ├── graph.py                 # create_agent + SqliteSaver + SqliteStore + context_schema=AgentContext
│   │   │   ├── runner.py                # invoke(context=AgentContext) + events stream
│   │   │   ├── state.py                 # CustomAgentState
│   │   │   ├── middleware.py            # @dynamic_prompt natif + wrap_tool_call (forçage user_id mémoire ET learning)
│   │   │   ├── prompts.py               # Core Prompt (règle 12 renforcée, règle 15 V6 : enregistrement obligatoire)
│   │   │   ├── tools.py                 # all_tools (24 = 3 base + 7 mémoire + 7 pédago + 4 learning + 3 code)
│   │   │   ├── memory.py                # MemoryFacts — SqliteStore ("users","profile",u)
│   │   │   ├── pedagogical_tools.py     # 7 tools pédago + AUTO-OBSERVATION V6 dans evaluate_answer
│   │   │   └── learning_tools.py        # [V6] 4 tools learning
│   │   ├── context/                      # Context Engineering V5+
│   │   │   ├── schemas.py               # AgentContext, RoutingResult, BuiltContext (learning: dict|None)
│   │   │   ├── router.py                # RoutingResult pydantic
│   │   │   ├── builder.py               # 7 sources → BuiltContext (source 7 learning V6)
│   │   │   ├── prompt_builder.py        # présentation pure + bloc ## LEARNING (V6)
│   │   │   ├── knowledge_retriever.py
│   │   │   ├── user_context.py / thread_context.py
│   │   ├── learning/                     # [V6 NOUVEAU] Learning Profile
│   │   │   ├── schemas.py               # LearningProfile, SubjectLearningState, TopicLearningState,
│   │   │   │                            #   LearningObservation, LearningGoal, LearningContextInfo
│   │   │   ├── learning_profile.py      # CRUD Store ("users","learning",u) + Profile Updater (formule §15)
│   │   │   │                            #   + validate_observation_targets (§18) + resolve_registry_topic
│   │   │   └── learning_context.py      # get_learning_context (§41) — sélection pertinente §24/§25
│   │   ├── subjects/                     # registry.py, taxonomy.py, tool_registry.py, definitions/*.yaml
│   │   ├── knowledge/                    # bases .md par matière (informatique/python/*.md …)
│   │   ├── api/                          # users, threads, chat, memory, logs, health, subjects,
│   │   │                                 # context.py (V5) + learning.py [V6 : 5 routes GET]
│   │   ├── db/                           # connections, users, threads
│   │   └── logging/                      # events.py (EventBus/log_event — events LEARNING_* natifs), sse
│   └── tests/
│       ├── test_v5_architecture.py       # 30/30 (régression V5)
│       ├── test_v5_integration.py        # 10/10 (régression V5)
│       ├── test_v6_learning.py           # [V6] 35/35 architecture A-J + §§46-48
│       └── test_v6_integration.py        # [V6] serveur LLM (6/11 — voir 32.6)
├── frontend/
│   └── src/
│       ├── api/                          # base, subjects, learning.ts [V6]
│       ├── components/
│       │   ├── memory/LearningProfileCard.tsx  # [V6] barre mastery ███░░ %, strengths/weak, goals, mode raw (§35/§36)
│       │   ├── memory/ContextInspectorCard.tsx # + section learning (source n°7)
│       │   └── … (Chat, Sidebar, LongTermMemoryCard, …)
│       ├── hooks/  (useSelection, useMemory, …)
│       ├── pages/  (ChatPage, LogsPage, MemoryPage + LearningProfileCard intégré)
│       └── types/  # agent.ts (TOOL_NAMES 24, preview.learning), learning.ts [V6]
├── RAPPORT.md
└── (checkpoints.db / long_term_memory.db / agent.log — runtime, non versionnés)
```

### 32.8. Limitations (honnêtes)

1. **Tests intégration LLM non re-vérifiés après le dernier fix** (serveur obsolète diagnostiqué, port libéré) — l'architecture (35/35) et le fix unitaire sont verts, le run serveur reste à refaire.
2. **Topics bilingues non fusionnés** : `fonctions` et `functions` sont deux topics Registry DISTINCTS dans le profil — le router route en FR (`fonctions`), le LLM peut enregistrer en EN ; pas de fusion d'alias (limite héritée du Registry V4).
3. **Mastery = scoring lexical** : couverture de termes-clés du cours (evaluate_answer), pas une mesure sémantique — c'est une estimation (§9 documenté, confidence bornée).
4. **Auto-observation liée à evaluate_answer** : une évaluation où le LLM ne passe PAS par le tool (jugement direct malgré la règle 12) ne produit pas d'observation.
5. `resolve_registry_topic` est lexical : une section .md sans lien Registry (ex: `_intro` d'un fichier non mappé) est rejetée — l'observation est perdue (loggée), pas inventée.
6. Le sujet routing (§46) reste lexical V4 — un sujet mal routé sélectionne le mauvais contexte learning (déjà le cas en V5 pour knowledge).

### 32.9. Prochaine étape — comment V6 prépare V7→V10

- **V7 Learning Engine** : `get_learning_context(user_id, subject, topic)` (§41) est l'interface stable attendue ; l'historique des 50 dernières observations (§33) permet d'analyser la trajectoire (régression, plateau) et de décider des STRATÉGIES (révision espacée, sélection du prochain topic) ; l'observation est séparée de l'update (§13) — le Engine s'intercale entre les deux sans rien réécrire.
- **V8 User Knowledge / RAG** : le Learning Profile ne dépend PAS du knowledge (§42) — remplacer le retriever lexical par des embeddings ne touche pas au profil ; le Context Builder rassemblera les deux sources.
- **V9 Code Practice** : `execute_code`, `run_tests`, `analyze_code` existent déjà — ils pourront émettre des LearningObservations type "exercise" via le même pipeline (le type est déjà dans le Literal §12).
- **V10 HITL** : la séparation Observation → Profile Updater permet d'insérer une approbation humaine avant `update_profile_from_observation` (§43 : observation → important update → human approval → profile update) sans changer les schémas.

**Conformité §51** : persiste cross-thread ✅ (F) · persiste après restart ✅ (H, Store) · isolation ✅ (G) · observations séparées ✅ (§47 ordre des logs) · subject/topic structurés ✅ · mastery+confidence ✅ · weak_points ✅ · strengths ✅ · attempts ✅ · goals ✅ · contexte learning alimenté ✅ (I) · sélection pertinente ✅ (§48) · User Memory séparée ✅ (namespaces) · Thread State séparé ✅ · aucun message stocké ✅ (§34) · aucun Learning Engine ✅ (§40) · aucun multi-agent ✅ · aucun HITL ✅ · aucun RAG ✅ · aucun tool spécialisé par matière ✅ · tests architecture 35/35 ✅ · frontend build ✅ · structure réelle incluse ✅ — intégration serveur : 6/11 avec cause identifiée et fix prêt (à re-run). Aucun commit créé (§51 : Git traité séparément).

---

# 33. MISSION INTÉGRATION FINALE — fusion V5.2 + V6, bugs, frontend, tests complets

**Date :** 12 septembre 2026
**Branche :** `master` (checkout fait en début de mission — cf. §33.A)
**Objectif :** fusionner les travaux parallèles V5.2 (Tools pédagogiques + Code Practice) et V6 (Learning Profile), corriger les bugs identifiés, compléter le frontend, exécuter TOUTES les suites de tests, produire un rapport final complet et cohérent sur la branche principale.

---

## 33.A. État Git et fusion (§41-A)

| Point | Vérifié |
|---|---|
| Branches `master` et `mission/v5.2-pedagogical-tools` | Pointaient toutes deux sur `f6dbc52` — **aucune divergence** : les deux agents ont travaillé séquentiellement dans le même working tree |
| Checkout `master` | Effectué en début de mission — le travail non-committé (V5.2 + V6) a été **transporté intact** (rien de perdu, aucune opération destructive) |
| Conflits de fusion | **Aucun** — la « fusion » était déjà sémantiquement présente dans le working tree (les deux agents ont édité les mêmes fichiers l'un après l'autre) |
| Fichiers modifiés | 19 modifiés + 21 nouveaux = **40 fichiers** (cf. §33.B pour le détail) |
| Architecture parallèle créée ? | **NON** — la contrainte « NE PAS créer de nouvelle architecture parallèle » est respectée : V5.2 s'est greffé sur V6 via les points d'extension prévus (state, prompts, tools, main) |

### Matrice de fusion vérifiée (audit initial)

| Fichier | Apport V5.2 (greffé sur V6) | Intact ? |
|---|---|---|
| `state.py` | 3 champs : `learning_activity` (dict), `activity_log` (Annotated[list, operator.add]), `code_runs` (int) | ✅ |
| `prompts.py` | Règles 16-26 (workflow interactif des activités V5.2) ajoutées après la règle 15 (V6) | ✅ |
| `tools.py` | `all_tools = 3 base + 7 memory + 7 pédagogiques + 4 learning + 3 code = 24 tools` | ✅ |
| `schemas.py` | 5 classes V5.2 (ActivityState, ActivityEvent, CodeRunResponse...) après le champ learning V6 | ✅ |
| `main.py` | 2 routers ajoutés : `learning` (V6) + `activity` (V5.2) | ✅ |
| YAML (4) | python : +specialized code tools ; les 3 autres : common only | ✅ |
| `context/*` (V5) | Non touchés par V5.2 | ✅ intacts |
| `learning/*` (V6) | Non touchés par V5.2 | ✅ intacts |

---

## 33.B. Bugs corrigés (§41-B)

### Bug #1 — `run_tests` : comparaison faux-négative (0/3)

**Symptôme :** code correctement écrit par l'étudiant marqué FAIL (« Expected '5', got '5' »).
**Cause :** le harness généré comparait `_actual == {expected_repr!r}` — quand le LLM passait `"5"` (str) au lieu de `5` (int), `repr("5") = "'5'"` mais l'exécution produisait `"5"` → comparaison str/repr incohérente.
**Fix :** double comparaison au moment de la génération du harness (`code_tools.py`, ~ligne 700) : `'passed': _actual == {expected_repr} or _actual == {str(expected)!r}` — validé par exécution réelle isolée (2 PASS / 1 FAIL exact, le FAIL étant un vrai faux code).

### Bug #2 — `test_v52_unit` 44b : test mono-tour comprimé

**Symptôme :** le test compressait evaluate_answer + assess_understanding dans le même tour → l'activité passait `completed` avant que `checking_understanding` ne soit observable.
**Fix :** scénario réaliste multi-tours (tests/test_v52_unit.py) : tour 2 = réponse (evaluate_answer + 44a/44c), tour 3 = explication de l'étudiant (assess_understanding + 44d vérifié APRÈS relecture de l'activité). **58/58 PASS** après fix.

### Bug #3 — `test_v52_unit` 50c : topic « loops » sans section réelle

**Symptôme :** `create_exercise(python, "loops")` — « loops » est un topic REGISTRY mais pas une SECTION de fichier (`loops.md` a _intro/for/while/range/break-continue/comprehensions).
**Fix :** test corrigé vers `while` (section réelle). **En amont**, ce bug a révélé le problème architectural plus profond → **Pont Registry ↔ knowledge** (cf. §33.C).

---

## 33.C. Le pont Registry ↔ knowledge — fix architectural majeur

**Problème racine (diagnostiqué via V6-int 6/11) :** le router V4 route des topics **REGISTRY** (« fonctions », présents dans `python.yaml:topics`), mais les fichiers knowledge sont découpés en **SECTIONS** (`definition`, `return`, `parametres`...). Quand le LLM appelait `create_exercise(python, "_intro")` (la section vue dans le bloc knowledge du contexte), `_find_section` résolvait `_intro` vers le **premier fichier** (basics.md) → exercice sur le mauvais contenu → score 0.0 → `resolve_registry_topic` → None → auto-observation silencieusement ignorée.

**Fix en 4 couches (sans aucun `if subject ==`, sans hardcoding de matière) :**

1. **`resolve_topic_source(subject, topic)`** (knowledge_retriever.py — fonction additive) : résout un topic Registry vers son fichier knowledge par (a) stem exact (`functions` → functions.md) ou (b) token du titre H1 (« fonctions » ⊂ « Python — Fonctions »). Retourne `(source_yaml, stem)` ou None.
2. **`_find_section`** (pedagogical_tools.py) : (a) le topic EST une section → comportement V4.1 inchangé ; (b) **`_intro` est REJETÉ** (ambigu : chaque fichier en a un) ; (c) sinon pont Registry → fichier résolu → **première section réelle** (`fonctions` → functions.md/`definition`, `boucles` → loops.md/`for`, `cellule` → cell.md/membrane).
3. **Canonisation** (`resolve_registry_topic`, learning_profile.py) : les topics Registry pointant vers le MÊME fichier convergent vers une seule clé de profil (`fonctions` ≡ `functions` → clé `functions`) — le router FR et le tool EN ne créent plus deux progressions divergentes.
4. **Fallback canonique** (`get_learning_context`, learning_context.py) : si le router route `fonctions` mais que le profil indexe `functions`, la progression réelle est affichée (même fichier ⇒ même progression), sans inventer de topic.

**Validations :**
- Unitaires (9 cas python + 2 biology) : `fonctions/functions`→`functions/definition`, `boucles/loops`→`loops/for`, `while`→`loops/while`, `return`→`functions/return`, `cellule`→`cell/membrane`, `_intro`→None ✅
- V6-integration : **6/11 → 11/11** (IT2 observation enregistrée, IT3 progression vue cross-thread, IT7/7b/8 mastery évolutif 0.29→0.42 selon la formule §14)
- Aucune régression : V6-arch 35/35, V5-arch 30/30, V5.2 58/58 restés verts

### Fix comportemental complémentaire (création immédiate)

**Symptôme :** le LLM demandait « quel aspect des fonctions ? » au lieu de créer l'exercice — entraînait l'échec des parcours 30a/35/37.
**Fix (2 fichiers) :** (a) règle 17 du prompt : « CRÉATION IMMÉDIATE : si l'étudiant demande un exercice sur un sujet, appelle create_exercise IMMÉDIATEMENT avec ce sujet — le tool résout lui-même la section knowledge. Ne demande PAS à l'étudiant de choisir un sous-aspect. » ; (b) docstring de `create_exercise` réécrite (l'ancienne « Utilise give_hint level=0 pour découvrir les topics » encourageait l'énumération). **Parcours E2E 15/19 → 19/19.**

---

## 33.D. Tools fusionnés — 24 tools, responsabilités (§41-C)

| Groupe | Tools | Responsabilité |
|---|---|---|
| Base (3) | `additionner`, `calculer_longueur_texte`, `recherche_web` | Démonstration initiale (prototype → V4) |
| Memory (7) | `get_user_profile`, `update_user_profile`, `save_user_memory`, `get_user_memory`, `search_user_memory`, `update_user_memory`, `delete_user_memory` | Mémoire longue durée cross-thread (SqliteStore, namespaces users/profile + users/memory) |
| Pédagogiques (7) | `create_exercise`, `evaluate_answer`, `give_hint`, `create_quiz`, `create_quiz_next`, `assess_understanding`, `propose_review` | Workflow interactif V5.2 — exercice → attente → évaluation → hint progressif → compréhension |
| Learning (4) | `get_learning_profile`, `get_learning_topic`, `update_learning_goal`, `record_learning_observation` | Lecture/écriture du Learning Profile (V6) |
| Code (3) | `execute_code`, `run_tests`, `analyze_code` | Pratique du code sandboxée — réservés python via YAML specialized (§39) |

**Cohérence YAML ↔ implémentation (§25) :** audit révélé 3 tools déclarés mais non implémentés (`analyze_diagram`, `verify_solution`, `symbolic_calculation`) — le Tool Registry les aurait loggés unavailable (§39, jamais exposés au LLM), mais la mission exige la cohérence : **retirés des YAML** biology/mathematics. Vérifié : 4 matières, **0 tool fantôme** (python 9 declares = 6 common + 3 specialized réels ; les 3 autres : 6 common chacun).

### Champs CustomAgentState (§41-D)

| Champ | Type | Rôle | Origine |
|---|---|---|---|
| `user_id` | str | Identifiant pour mémoire/checkpointer | Prototype |
| `interaction_count` | int | Compteur d'interactions du thread | V4 |
| `learning_activity` | dict | Activité pédagogique thread-locale (exercice en cours, status, hint_level...) | V5.2 |
| `activity_log` | Annotated[list, operator.add] | Journal des événements d'activité (réduction additive LangGraph) | V5.2 |
| `code_runs` | int | Compteur d'exécutions de code du thread | V5.2 |

---

## 33.E. Frontend complété (§41-E)

Composants V5.2 livrés (par subagent dédié, vérifiés par build dans cette mission) :

| Fichier | Rôle |
|---|---|
| `types/activity.ts` | Types ActivityState, ActivityEvent, CodeRunResponse |
| `api/activity.ts` | getThreadActivity / runCode via apiFetch |
| `components/chat/CodeEditor.tsx` | Éditeur avec gouttière numéros de ligne, Tab→2 espaces, bouton Play, vraies erreurs (400/403 remontées) |
| `components/chat/TestResultPanel.tsx` | Panneau résultats de tests (passed/failed/détail) |
| `components/chat/CodeAnalysisPanel.tsx` | Analyse de style réel (`_PY_STYLE_RULES`, principe §31) |
| `components/chat/ActivityFeed.tsx` | Flux d'événements avec icônes, polling 30s, ActivitySummary en header |
| `pages/MemoryPage.tsx` | Section Activity + carte Code Practice ajoutées — **rien de retiré** |
| `types/agent.ts` | TOOL_NAMES 17→24 |

**Vérifié dans cette mission :** `tsc -b` 0 erreur ; `vite build` ✓ (2.16s). Aucune régression frontend (le MemoryPage V6 LearningProfileCard intact).

---

## 33.F. Tests — résultats complets (§41-G)

| Suite | Fichier | Résultat |
|---|---|---|
| Architecture V5 | test_v5_architecture.py | **30/30 PASS** |
| Intégration V5 | test_v5_integration.py | **10/10 PASS** (BASE_PORT=8001) |
| Architecture V6 | test_v6_learning.py | **35/35 PASS** |
| V5.2 unitaires | test_v52_unit.py | **58/58 PASS** (3 bugs critiques corrigés → 0 FAIL) |
| Intégration V6 | test_v6_integration.py | **6/11 → 11/11 PASS** (pont Registry↔knowledge) |
| **Parcours E2E (§30-§39)** | test_final_integration.py (NOUVEAU) | **19/19 PASS** |

**Total : 163/163 — ZÉRO test critique en échec (§28).** Aucun test désactivé ni supprimé.

### Parcours E2E couverts (§30-§39)

| Test | Scénario réel LLM | Vérifié |
|---|---|---|
| 30a | « Donne-moi un exercice sur les fonctions » → create_exercise immédiat → waiting_for_answer | ✅ |
| 30b | Réponse riche → evaluate_answer → observation → Learning Profile attempts≥1 | ✅ |
| 30c | Activité thread-locale ≠ profil (pas de fuite) | ✅ |
| 31a-c | Code erroné → SyntaxError réelle → corrigé → success (run-code API) | ✅ |
| 32 | Activité persistée via checkpointer après les échanges | ✅ |
| 33a-b | Thread B : activité absente, profil/progression présents (cross-thread) | ✅ |
| 34a-c | User B : profil not_started, activité 403, run-code 403 (cross-user) | ✅ |
| 35 | « Bonjour » ≠ réponse — waiting_for_answer préservé | ✅ |
| 36 | « Je suis bloqué » → hint progressif (level 0 → 1) | ✅ |
| 37 | Réponse suffisante → évaluation → explication → fin propre (completed) | ✅ |
| 38 | Topic inexistant → pas d'invention, guidance | ✅ |
| 39 | Registry : python déclare les code tools, biology non (et 0 fantôme après nettoyage) | ✅ |
| 19 | Sandbox : code réseau (import socket) rejeté 400 | ✅ |

---

## 33.G. Audit d'architecture (§42 — 10 réponses explicites)

1. **« Est-ce que chaque matière a une implémentation distincte ? »** → **NON.** Zéro `if subject ==` dans le code des tools (vérifié par audit source : le seul match est un commentaire « Aucun if subject == 'python' »). Toute matière vit dans YAML + fichiers knowledge ; le code est générique. Les code tools sont réservés à python via `tools.specialized` du YAML (données, pas code).
2. **« Y a-t-il plusieurs systèmes de mémoire en parallèle qui se contredisent ? »** → **NON, 3 systèmes séparés par conception** : User Memory (préférences, SqliteStore namespace users/memory) ≠ Thread State (activité pédagogique du thread, checkpointer) ≠ Learning Profile (progression cross-thread, Store namespace learning). Chacun a sa source de vérité et ses tests d'isolation dédiés (34a-c : cross-user ; 33a-b : cross-thread ; §34 V6 : aucun message stocké).
3. **« Les tools simulent-ils du comportement ? »** → **NON.** evaluate_answer = scoring lexical déterministe sur les termes-clés de la section réelle ; give_hint = niveaux progressifs du contenu réel ; execute_code = subprocess isolé réel (verrous réseau/fichiers/secrets s1-s12) ; run_tests = harness généré réellement exécuté ; analyze_code = règles de style réelles.
4. **« Les réponses attendues sont-elles exposées ? »** → **NON.** `_EVAL_STOP_WORDS`/termes-clés ne sortent jamais des tools ; `summarize_activity()` est conçu pour ne jamais leaker la réponse attendue ; le ToolMessage renvoyé au LLM contient score/verdict, pas la solution.
5. **« Le thread-local est-il confondu avec le profil global ? »** → **NON.** `learning_activity` (dict thread-local via checkpointer) ≠ `subjects/{user}/learning` (profil cross-thread via Store) ; 30c/33a-b prouvent l'isolation dans les deux sens ; la progression du profil est visible depuis un autre thread, l'activité ne l'est jamais.
6. **« Les tools de code sont-ils sandboxés ? »** → **OUI.** Subprocess isolé (rundir dédié par run), scan du code AVANT exécution (import os/socket/subprocess/process → refus), secrets retirés de l'env du subprocess (s9), réseau bloqué (§19 : import socket → 400), fichiers restreints (s5-s8), sujet autorisé par YAML (s10-s12).
7. **« Les YAML et Knowledge sont-ils réutilisés ? »** → **OUI.** 4 YAML sources de vérité (topics, aliases, tools, knowledge.sources) ; 9 fichiers knowledge .md découpés en sections réelles ; le pont §33.C les relie sans duplication (aucune liste de topics codée en dur).
8. **« V5 intact ? »** → **OUI.** Router/builder/prompt_builder/knowledge_retriever/registry non altérés dans leur comportement V5 (retrait des faux tools YAML uniquement) ; V5-arch 30/30 + V5-int 10/10 le prouvent après la fusion complète.
9. **« LangChain/LangGraph natifs ? »** → **OUI.** create_agent v1, InjectedState/InjectedToolCallId, Command(update=), Annotated[list, operator.add] pour activity_log, SqliteStore/SqliteSaver, checkpointer natif. Aucune réimplémentation parallèle d'un mécanisme natif.
10. **« Des fichiers temporaires/debug sont-ils restés ? »** → **NON.** `_scratch_agent_pattern.py` supprimé ; scan `*_scratch*|*_debug*|*_tmp*|*test_manual*` sur tout le projet : 0 résultat. Seule exception documentée : `database/code_runs/` (runs réels des tests, données runtime, pas du code).

---

## 33.H. Arbre réel du projet (§40)

```
backend/
  app/
    agent/  graph.py runner.py state.py middleware.py prompts.py tools.py
            memory.py pedagogical_tools.py (1430 l.) code_tools.py (V5.2)
            activity_state.py (V5.2) learning_tools.py (V6)
    api/    chat.py users.py threads.py memory.py context.py subjects.py
            logs.py health.py schemas.py learning.py (V6) activity.py (V5.2)
    context/ router.py builder.py prompt_builder.py knowledge_retriever.py
             schemas.py thread_context.py user_context.py tool_context.py
    learning/ learning_profile.py learning_context.py schemas.py (V6)
    subjects/ registry.py schema.py taxonomy.py tool_registry.py
              definitions/ python.yaml biology.yaml mathematics.yaml
                           computer_networks.yaml
    knowledge/ informatique/python/{basics,functions,loops,oop}.md
               informatique/reseaux/{osi_model,tcp_ip}.md
               mathematics/algebre/equations.md
               sciences/biologie/{cell,genetics}.md
    db/ users.py threads.py connections.py
    logging/ events.py sse.py    ws/ logs.py
    main.py config.py
  tests/ test_v5_architecture.py test_v5_integration.py test_v52_unit.py
         test_v6_learning.py test_v6_integration.py
         test_final_integration.py (§30-§39)
frontend/src/
  components/chat/ ChatPanel.tsx CodeEditor.tsx TestResultPanel.tsx
                   CodeAnalysisPanel.tsx ActivityFeed.tsx
  components/memory/ MemoryPage cards + LearningProfileCard.tsx
                     ContextInspectorCard.tsx
  pages/  api/  types/ (activity.ts learning.ts agent.ts 24 tools)
logs/agent.log   database/ (checkpoints.db long_term_memory.db code_runs/)
```

---

## 33.I. Limites restantes (§41-K)

1. **Scoring lexical** : evaluate_answer évalue la couverture des termes-clés — une réponse reformulée sans les mots attendus peut sous-évaluer (le LLM compense en feedback). Piste : observer aussi via record_learning_observation direct (le tool existe, type "exercise" au Literal §12).
2. **Pont FR→sections à une entrée** : `fonctions` → `definition` (première section réelle). Le LLM peut toujours demander explicitement `return`/`parametres` pour cibler. Un mapping topic→section plus riche serait une donnée YAML (pas du code).
3. **Le routing de sujet reste lexical V4** (inchangé depuis V5, connaissance du contexte).
4. **Uniquement les matières avec knowledge réel** (python, biologie, réseaux, maths) — ajouter une matière = YAML + fichiers .md, zéro code.
5. **§32 persistance inter-restart du flux activity** : prouvé unitairement via checkpointer (§49 V5.2) et l'activité reste lisible après tous les échanges E2E (32) ; un run serveur kill/relance pendant un exercice en cours reste à scripter si on veut la trace HTTP complète.

---

## 33.J. Conformité aux contraintes de la mission

| Contrainte | Statut |
|---|---|
| Tout finalisé sur la branche principale (`master`) | ✅ checkout master, 40 fichiers, toutes suites vertes |
| NE PAS créer d'architecture parallèle | ✅ greffe par points d'extension (state/prompts/tools/main/YAML) |
| NE PAS supprimer les travaux valides V5/V6 | ✅ context/* et learning/* intacts ; tests V5/V6 tous verts après fusion |
| 3 bugs du rapport V5.2 corrigés | ✅ §33.B (#1 run_tests, #2 44b multi-tours, #3 50c + pont racine) |
| Frontend complet | ✅ 8 composants/fichiers + build tsc+vite verts |
| TOUTES les suites exécutées | ✅ 6 suites, 163/163 |
| Nouveaux tests E2E §30-§39 | ✅ 19/19 (test_final_integration.py) |
| ZÉRO test critique en échec (§28) | ✅ 0 FAIL — aucun test désactivé/supprimé |
| Rapport final §41 A-K + §42 (10 questions) + §40 arbre | ✅ §33.A à §33.I ci-dessus |
| §44 interdits (RAG/Qdrant/Langfuse/OTel/Multi-Agent/HITL/User Document Knowledge) | ✅ aucun ajouté |
| Git : état master finalisé | ✅ working tree master propre, commit à la discrétion du porteur (§33.K) |

---

## 33.K. Récapitulatif final

- **Fusion :** V5.2 (Tools pédagogiques + Code Practice) et V6 (Learning Profile) fusionnés sur `master` sans conflit, sans architecture parallèle, sans suppression de travaux valides.
- **Bugs :** 3 corrigés + 1 racine architecturale (pont Registry↔knowledge en 4 couches) + 1 comportemental (création immédiate) — cascade complète V6-int 6/11 → 11/11.
- **Frontend :** complété et vérifié (tsc 0 erreur, vite build ✓).
- **Tests :** 6 suites, **163/163 PASS** — dont 19 parcours E2E réels §30-§39 avec LLM réel (gemma4:31b-cloud via Ollama).
- **Audit §42 :** 10/10 réponses conformes (§33.G).
- **Branche master :** état final cohérent et stable.

---

**Fin du rapport de mission intégration.** Le système est désormais un tuteur IA complet : routing de matière, contexte structuré, mémoire longue durée, activités pédagogiques interactives avec workflow multi-tours, pratique du code sandboxée, et profil d'apprentissage persistant cross-thread — le tout testé de bout en bout sur la branche principale.

---

# 34. MISSION V6.5 — SEARCH, RETRIEVAL & FALLBACK QUALITY

**Date :** 12 septembre 2026
**Branche :** `master`
**Objectif :** améliorer ROUTING + KNOWLEDGE RETRIEVAL + WEB SEARCH + FALLBACK — paraphrases, questions vagues, knowledge insuffisant, sujets inconnus, recherches web, absence de résultats, résultats peu pertinents. SANS RAG vectoriel, SANS Qdrant, SANS nouveau modèle obligatoire (§40/§41 respectés).

---

## 34.A. Architecture de recherche (§42-A)

```
USER QUERY
    ↓ normalize_query (§8 : accents/casse/ponctuation/whitespace)
ROUTER déterministe (Registry YAML : aliases + topics)
    ↓ variantes morphologiques (fonction ≈ fonctions, §8)
    ↓ aliases multi-mots par COUVERTURE de tokens (ordre libre)
    ↓ confidence graduée : 0.95/0.85 (phrase exacte) · 0.80 (tokens, paraphrase) · 0.55 (topic seul)
    ↓ status : supported / ambiguous (candidates) / unsupported / unknown / multi_domain
SUBJECT/TOPIC
    ↓
LOCAL KNOWLEDGE (search_knowledge §4)
    formule composite §42-C → tri → seuil 0.3 → top_k
    ↓
résultat suffisant ? (items ≥ 1)
 ┌───────────┴───────────┐
 oui                     non (insufficient + matière supportée §16)
 ↓                       ↓
CONTEXT              WEB SEARCH (web_search §17)
                         plan §18 → Ollama web_search → normalisation §20
                         ranking §21 → seuil 0.15 → top_k §22
                         ↓
                    suffisant ?
                    ┌────┴────┐
                   oui       non / error / unavailable
                   ↓           ↓
                CONTEXT    GENERAL TUTOR (§25, transparent)
```

Jamais de recherche web pour `unknown` (§36 noise) ni `unsupported` (§15 : pas d'ancrage de matière, pas de SubjectConfig fabriqué).

---

## 34.B. Schéma de recherche (§42-B)

`SearchResult` (context/schemas.py) — unifié pour TOUTES les sources :

| Champ | Type | Rôle |
|---|---|---|
| `title` | str | Titre lisible (« Python — Fonctions », titre web) |
| `source` | str | python/functions, docs.python.org |
| `url` | str\|None | None si local |
| `content` | str | Contenu exploitable |
| `snippet` | str\|None | Extrait court (web) |
| `relevance` | float [0..1] | Formule §42-C |
| `source_type` | Literal | local_knowledge / web / user_document / other — **Literal protégé, jamais inventé** (test 3b) |
| `metadata` | dict | Internes (section, source_quality) — **jamais dans le prompt** (§27, testé) |

`SearchResponse` : `status: Literal[found, insufficient, unavailable, error]` + `query` (normalisée) + `results: list[SearchResult]`. « found = [] » n'existe plus (§23 : chaque échec a son statut, tests 33a/33b).

`KnowledgeResult` hérite `SearchResult` (source_type=local_knowledge + champ topic pratique) — pas de duplication. `BuiltContext.web : SearchResponse` (default status=unavailable = aucune tentative). `KnowledgeSearchResult` compat V5 conservée.

---

## 34.C. Formules de ranking (§42-C) — documentées et testées

**Knowledge local (knowledge_retriever.py)** :

```
relevance = 0.30 × topic_score      (section exacte 1.0 / variante morphologique 0.5)
          + 0.25 × title_score      (couverture tokens requête par le titre H1 du fichier)
          + 0.20 × phrase_score     (requête entière 1.0 / sous-phrase ≥2 mots 0.4+0.15×taille)
          + 0.15 × content_score    (containment tokens, stop-words retirés)
          + 0.10 × subject_score    (matière ou alias §9 explicite dans la requête)
```

Le topic reste dominant (0.30) : « c'est quoi return » → section `return` avant `definition` (test 34c). Pont Registry↔knowledge V6 **INTACT** (§5 : fonctions→functions.md, boucles→loops.md, cellule→cell.md — retestés).

**Web (web_search.py)** :

```
web_relevance = 0.35 × coverage   (tokens requête web couverts par titre+contenu)
              + 0.20 × title     (tokens dans le titre)
              + 0.15 × topic     (topic du routing matche)
              + 0.20 × source_quality  (docs.python.org 1.0, MDN/w3/IETF 0.9, Wikipedia 0.7, Khan/OC 0.6, inconnu 0.0)
              + 0.10 × content   (tokens dans le contenu)
```

Coverage domine (0.35) : un résultat hors-sujet reste hors-sujet même officiel. Source quality départage à coverage égal ; domaine inconnu = 0, **aucune source officielle fabriquée** (§19, test 19). Seuil web 0.15, top_k 3 par défaut.

**Variantes morphologiques (query_norm.py, §8)** : accents NFD, lowercase, ponctuation→espace, whitespace collapsé, singulier contrôlé (s/es finaux, mots ≥4 lettres). Générique par règles de suffixe — **zéro `if subject ==`**, aucune liste de matières.

---

## 34.D. Matrice de fallback (§42-D)

| Situation | Action | Testé |
|---|---|---|
| supported + knowledge found | contexte local (web non tenté) | 37a, v5/v6-int |
| supported + insufficient | web search (matière supportée §16) | 32a-c (asyncio réel → 0.76 docs.python.org) |
| web found | contexte web + knowledge note | §27 (RECHERCHE WEB dans prompt) |
| web insufficient/unavailable/error | General Tutor transparent | 33a/33b + prompt note |
| ambiguous | clarification (candidates, aucun choix inventé) | 31 |
| unknown | General Tutor / clarification, **zéro recherche web** | 36a-c |
| unsupported | General Tutor (aucune config/knowledge/tool fabriqué) | S50 v5-arch |
| search error | fallback, agent continue, WEB_SEARCH_ERROR loggé | 33b |

---

## 34.E. Tests — résultats exacts (§42-E)

| Suite | Résultat |
|---|---|
| test_v5_architecture.py | **30/30 PASS** |
| test_v6_learning.py | **35/35 PASS** |
| test_v52_unit.py | **58/58 PASS** |
| **test_v65_search.py (NOUVEAU)** | **23/23 PASS** |
| test_v5_integration.py | **10/10 PASS** |
| test_v6_integration.py | **11/11 PASS** |
| test_final_integration.py | **19/19 PASS** |

**Total : 186/186 PASS (163 régression + 23 nouvelles), zéro échec critique (§39 > 163/163 requis).**

Nouveaux tests §30-§38 : 30a paraphrase ordinateurs→computer_networks 0.80 · 30b variantes morphologiques · 31 ambiguïté réseaux conservée · 32a-b knowledge absent→web (insufficient détecté, tentative effectuée) · 33a clé absente→unavailable · 33b exception→error sans crash · 34a-c ranking pertinent>non-pertinent (web + knowledge) · 35 top_k 10→3 · 36a-c noise zéro recherche · 37a-b sources séparées (local≠web≠memory) · 38a-b routing indépendant du Learning Profile · 3a-b Literal protégés · 19 source quality sans invention.

---

## 34.F. Observabilité (§28)

Événements émis : `SEARCH_START` / `SEARCH_END` / `SEARCH_RESULT` / `SEARCH_NO_RESULT` (pipeline) · `WEB_SEARCH_START` / `WEB_SEARCH_END` / `WEB_SEARCH_ERROR` / `WEB_SEARCH_UNAVAILABLE` (web) · `KNOWLEDGE_SEARCH` / `KNOWLEDGE_SELECTED` / `KNOWLEDGE_UNAVAILABLE` (local, V5). Chacun porte user_id/thread_id/query/subject/topic/result_count/status (+best_relevance quand applicable). Grep anti-secrets : **aucune clé/token/credential loggée**.

---

## 34.G. Frontend (§29)

- `types/agent.ts` : `SearchResultItem` + `SearchWebResponse` + `ContextPreview.web?`
- `ContextInspectorCard.tsx` : section **search · web** (badge `status · N`, query affichée, best %, URLs, snippets) — masquée si aucune tentative (unavailable) ; en échec affiche « Web search {status} → fallback: General Tutor ». Aucun détail interne (source_quality) exposé.
- `api/schemas.py` : `ContextPreviewResponse.web` exposé.
- Gates : `tsc -b` 0 erreur, `vite build` ✓.

---

## 34.H. Hardcodes et heuristiques nouvelles (§42-G)

| Heuristique | Localisation | Générique ? |
|---|---|---|
| Pondérations ranking (0.30/0.25/0.20/0.15/0.10, web 0.35/0.20/0.15/0.20/0.10) | constantes nommées documentées | oui — aucune matière |
| Variantes morphologiques (s/es/x) | query_norm.py, règles de suffixe | oui |
| Aliases enrichis (ordinateurs communiquent, closures, decorateurs, generateurs) | YAML matières (source déclarative §9) | oui — données, pas code |
| Domaines éditoriaux (docs.python.org 1.0…) | web_search.py `_OFFICIAL_DOMAINS` | **documenté** : liste de domaines éditoriaux transverses, pas de matière ; extensible en données si besoin |
| Seuils 0.3 (local) / 0.15 (web) | constantes nommées | oui |

Zéro `if subject ==` dans le code (re-vérifié).

## 34.I. Limitations honnêtes (§42-H)

1. **Tout reste lexical** (§40 : pas d'embeddings) — la pertinence est un matching de tokens/variantes, pas sémantique. Une paraphrase sans aucun mot-racine commun (ex. « fermetures » pour closures) reste invisible au router tant qu'aucun alias YAML ne la couvre.
2. **La reconnaissance de paraphrase dépend des aliases YAML** — « Comment communiquent les ordinateurs » est reconnu parce que l'alias est déclaré ; ce n'est pas de la compréhension. Étendre la couverture = enrichir le YAML (voulu, source déclarative).
3. **Le singulier morphologique est heuristique** — mots ≥4 lettres, s/es finaux ; « cours » (déjà singulier) n'est pas touché (règle x désactivée), mais des faux-positifs restent possibles sur de rares pluriels irréguliers.
4. **Web search dépend du service Ollama cloud** — quand il échoue, le statut est propre (unavailable/error) et le General Tutor prend le relais, mais aucune recherche alternative n'existe (§41 : pas de nouveau provider).
5. **Topic exact vs ambigu dans une requête multi-topics** — « le return des fonctions » route sur le premier topic YAML matché (fonctions) ; acceptable (le sujet est couvert), un désambiguïsateur pondéré serait une évolution.
6. **Le semantic fallback du router (§11-§12)** est ici purement lexical (variantes + couverture tokens) — conforme à la mission (« peut rester simple »), mais ce n'est pas du sémantique au sens embeddings.

---

## 34.J. Definition of Done (§43) — vérifiée

| Critère | Statut |
|---|---|
| ✅ SearchResult structuré | §34.B, Literal protégé (test 3b) |
| ✅ SearchResponse structuré | status 4 valeurs (test 3a) |
| ✅ local knowledge ranking amélioré | formule composite §34.C (test 34c) |
| ✅ web search structuré | web_search.py + recherche_web reconnecté |
| ✅ fallback search fonctionnel | pipeline §34.A (asyncio réel found 0.76) |
| ✅ unknown/ambiguous/unsupported propres | 31/36a-c/S50 |
| ✅ relevance score | documenté + testé |
| ✅ top_k | test 35 (10→3) |
| ✅ observabilité | §34.F |
| ✅ frontend inspector | §34.G |
| ✅ paraphrase test | 30a/30b |
| ✅ web failure test | 33a/33b |
| ✅ no invention | §26 (knowledge jamais found, domaines 0, unknown sans matière) |
| ✅ 163/163 régression | 186/186 (163 + 23) |
| ✅ aucun RAG vectoriel | zéro embedding/vector DB |
| ✅ aucun nouveau provider obligatoire | Ollama existant uniquement |

---

**Fin du rapport V6.5.** Le socle 163/163 est intact, enrichi de 23 tests search/retrieval/fallback : le router reconnaît les paraphrases déclarées avec confiance graduée, le knowledge local est classé par formule composite documentée, la recherche web est structurée (plan → normalisation → ranking → top_k → statut), et le pipeline local→web→General Tutor est fonctionnel, observable et testé de bout en bout — sans une ligne de RAG vectoriel ni de nouveau provider.

---

# 35. MISSION V6.6–V6.8 — FINALISATION DU SOCLE AVANT LEARNING ENGINE

État de référence vérifié avant toute modification (§3) : `git status` propre, branche `master`, dernier commit `7ea14bc`, suite de référence **186/186 PASS** (V5-arch 30, V5-int 10, V5.2 58, V6-arch 35, V6-int 11, V6.5 23, E2E 19). Aucun test supprimé ni désactivé.

Objectif (§1) : combler les trois dernières exigences architecturales AVANT le Learning Engine — Fallback Intelligence (V6.6), Structured Agent Output + UX (V6.7), Context Budget + Model Capability Management (V6.8). Interdits respectés (§2) : pas de RAG vectoriel, pas de Qdrant, pas d'embeddings, pas de reranking externe, pas de Langfuse/OTel/LiveKit/MCP/HITL/Multi-Agent, pas de User Document Knowledge, pas de Learning Engine, pas de nouveau provider ni modèle obligatoire.

Architecture livrée (§57) :

```text
USER → ROUTER (subject/topic/confidence/status)
     → RETRIEVAL (local knowledge + web)
     → FALLBACK DECISION (matrice pure V6.6)
     → CONTEXT BUILDER (memory + learning + thread + knowledge
                        + search + activity)
     → CONTEXT BUDGET (V6.8)
     → DYNAMIC PROMPT → LLM → TOOLS/ACTIONS
     → RESPONSE NORMALIZER (V6.7)
     → AgentResponse → FRONTEND RESPONSE RENDERER
```

---

## 35.A. V6.6 — Fallback Intelligence (§4-§15)

### A.1 Le modèle de décision

Nouveau module `app/context/fallback.py` + schéma `FallbackDecision` (`app/context/schemas.py`) — une **couche de décision** entre RoutingResult et SearchResponse qui ne duplique ni l'un ni l'autre (§5) :

| Champ | Rôle |
|---|---|
| `action` | Literal des 5 actions §6 : `use_local_knowledge`, `use_web_search`, `ask_clarification`, `use_general_tutor`, `continue_without_external_search` |
| `reason` | Raison lisible, non générique (« not found » interdit §7) |
| `source_status` | Concaténation documentée des états d'origine (ex. `supported/insufficient/web_error`) — les états ne sont **jamais** convertis silencieusement |
| `confidence` | Confiance de la décision [0..1] |
| `candidates` | Matières candidates si clarification (rempli par le builder sur routing ambiguous, §10) |

### A.2 La matrice de décision (§6) — pure et testable sans LLM

`decide_fallback(routing_status, knowledge_status, web_status, has_web_results, query)` est une **fonction pure** (aucun LLM, aucun appel externe) — toute la matrice §6 vit dans `_decide()` :

| Routing | Knowledge | Web | Action | Confiance |
|---|---|---|---|---|
| supported | found | non requis | use_local_knowledge | 0.95 |
| supported | insufficient/unavailable/error | found (résultats) | use_web_search | 0.70 |
| supported | insufficient | unavailable | use_general_tutor | 0.50 |
| supported | insufficient | error | use_general_tutor | 0.50 |
| supported | insufficient | insufficient | use_general_tutor | 0.50 |
| ambiguous | n/a | n/a | ask_clarification (+candidates) | 0.50 |
| unknown | n/a | n/a | ask_clarification **si vague** (§9) | 0.30 |
| unknown | n/a | n/a | use_general_tutor **si compréhensible** | 0.40 |
| unsupported | n/a | n/a | use_general_tutor | 0.90 |
| multi_domain | n/a | n/a | ask_clarification | 0.40 |
| statut inattendu | — | — | continue_without_external_search (défense) | 0.10 |

L'heuristique §9 « vague vs compréhensible » est documentée et testée : `is_vague_query()` compte les tokens alphabétiques (seuil < 3) — « Aide-moi » (1) → clarification ; « Pourquoi le ciel est bleu ? » (5) → general tutor.

Vérifié en dur avant intégration : **12/12 cas matriciels** corrects (script de debug, ensuite couverts par les tests).

### A.3 Les états jamais confondus (§7)

Chaque couche garde son vocabulaire — testé 11a/11b : `source_status = "supported/insufficient/web_error"` préserve les trois états distincts, et le `reason` est explicite (jamais « not found »). Le knowledge `error` local est replié en `insufficient` par la recherche V6.5 (l'erreur est loggée), le paramètre reste accepté pour la complétude du contrat ; `web_unavailable` (service/clé absente) et `web_error` (échec technique) produisent des raisons distinctes.

### A.4 Fallback transparent (§8) + intégration builder

Le builder (`app/context/builder.py`) appelle `decide_fallback()` après le pipeline search (§3c) : la décision est exposée dans `BuiltContext.fallback`, les candidates y sont injectées sur routing ambiguous, et `CONTEXT_BUILD_END` logge `fallback_action` + `fallback_reason`.

`fallback_note_for_prompt()` (§8) produit la note transparente pour le LLM — le prompt explique **la raison** du fallback au modèle (il peut la reformuler naturellement), ex. recherche web tentée → « appuie-toi sur la section RECHERCHE WEB et cite naturellement ces sources ». Le local knowledge ne produit **aucune** note (ce n'est pas un fallback). Le frontend étudiant n'affiche pas ces détails techniques (§32) — seule l'interface développeur (Context Inspector) les montre.

### A.5 §12-§13

- **supported + knowledge insufficient ≠ unsupported** (test 14) : le web est tenté, `source_status` reste préfixé `supported/` — la matière est configurée, c'est la base de cours qui manque.
- **web unavailable/error → General Tutor sans crash** (tests 3/4 + 15) : le builder survit au pipeline web complet, l'agent ne plante jamais.

### A.6 Observabilité (§14)

Events `FALLBACK_START` et `FALLBACK_DECISION` émis par `decide_fallback()`, portant user_id, thread_id, reason, action, subject, topic, routing_status, knowledge_status, web_status (testés 10a/10b, lus depuis agent.log). Zéro secret/API key/token loggé. `FALLBACK_ERROR`/`FALLBACK_END` : la fonction étant pure, l'erreur est impossible par construction — le statut inattendu est géré par `continue_without_external_search` (jamais de levée d'exception).

### A.7 Tests — `tests/test_v66_fallback.py` (§15) : **22/22 PASS**

Les 10 cas minimaux (1-10) + renforcements : heuristique vague (6c), états distincts (11a/b), transparence (12a/b/c), candidates réelles d'un build_context ambiguous (13 : computer_networks + neural_networks transmis), distinction insufficient/unsupported (14), no-crash builder web complet (15), Literal protégé (16).

---

## 35.B. V6.7 — Structured Agent Output + UX (§16-§35 + ADDENDUM)

### B.1 Le contrat `AgentResponse` (§17 + ADDENDUM)

Nouveau module `app/agent/response.py` — contrat stable et versionnable (`version: int = 1`) :

```python
type: Literal["text","exercise","quiz","evaluation","hint",
             "code","search","clarification","error"]
status: Literal["completed","waiting_for_user",
                "running","error","cancelled"]
message: str
data: dict[str, Any]
actions: list[dict[str, Any]]
```

**Les 5 couches d'état strictement séparées (ADDENDUM §1-§12)** — testées contractuellement :

| Couche | Enum | Inchangé depuis |
|---|---|---|
| AgentResponse.status (public) | completed / waiting_for_user / running / error / cancelled | **nouveau** |
| learning_activity.status (pédagogique) | idle / waiting_for_answer / evaluating / giving_hint / waiting_for_retry / checking_understanding / completed / abandoned | V5.2 |
| SearchResponse.status (retrieval) | found / insufficient / unavailable / error | V6.5 |
| RoutingResult.status (routing) | supported / ambiguous / unknown / unsupported / multi_domain | V4/V5 |
| FallbackDecision.action (décision) | 5 actions §6 | V6.6 |

`success` est **refusé** par le schéma public (ADDENDUM §7 — test : `AgentResponse(status="success")` lève une ValidationError). Un tool peut retourner `success` en interne pendant que l'AgentResponse est `completed` : deux vocabulaires, deux couches. Le flux complet ADDENDUM §9 est testé : `SearchResponse.insufficient → FallbackDecision.use_web_search → AgentResponse(type=text, status=completed)` — sans jamais changer le type de statut d'une autre couche.

Le statut `running` (ADDENDUM §4) reste réservé aux opérations utilisateur-visibles réellement en cours (ex. `evaluating`) ; les opérations internes restent des événements SSE (TOOL_START, SEARCH_START…) — pas de `running` artificiel.

### B.2 Response Normalizer (§26) — `app/agent/normalizer.py`

`normalize_response()` convertit les structures internes en AgentResponse, priorité : error → fallback clarification (candidates) → activité en cours → search utilisé → texte. Le **frontend ne connaît jamais les structures internes des tools**.

Mapping activity → AgentResponse (ADDENDUM §8, testé 10/10) — les deux machines à états restent distinctes :

| learning_activity.status | AgentResponse |
|---|---|
| waiting_for_answer (exercise/quiz/code) | exercise/quiz/code + waiting_for_user + actions submit_answer/request_hint |
| waiting_for_retry / checking_understanding | evaluation + waiting_for_user (backend vérifie, frontend attend) |
| giving_hint | hint + waiting_for_user (+hint_level) |
| evaluating | evaluation + running |
| completed | evaluation + completed |
| abandoned | evaluation + cancelled (≠ error) |

Sanitize §23 (défense en profondeur) : `expected_answer`, `hidden_answer`, `keywords`, `key_terms`, `scoring`, `answer` ne fuient **jamais** dans `data` (test : zéro leak sur un payload piégé). Le search n'expose que title/source/url/snippet — jamais `relevance` ni `source_quality` (§31).

Clarification §25 : `actions[0] = {type: "select", options: [...]}` → le frontend affiche des boutons sans parser le texte.

### B.3 Intégration pipeline (backend)

- `runner.run_agent()` : après le run, lit l'activité du state final + la FallbackDecision via le registre du middleware, normalise → `ChatResponse.agent_response` (le champ `response` texte reste : rétrocompatibilité totale).
- `run_agent_stream()` : l'événement SSE `ASSISTANT_MESSAGE` embarque désormais `agent_response` en plus de `response`.
- **Registre de contexte** (`app/agent/middleware.py`) : le dynamic_prompt stocke le dernier BuiltContext par thread_id (borné à 128, purge 64) — c'est ce qui permet au normalizer de voir routing/fallback/web du run courant. Registre en mémoire, dernier run gagne.

### B.4 Chemin robuste structured output (§33/§50)

Trois chemins documentés et hiérarchisés : structured output disponible → schema ; sinon → **ce normalizer** (normalisation contrôlée) ; sinon → texte standard (type=text). Le registre de capacités V6.8 (`supports_structured_output`) pilotera ce choix — à ce jour le modèle actif n'utilise pas le structured output natif, c'est donc le normalizer qui s'applique (chemin par défaut, déjà robuste). Une incapacité de structured output ne casse jamais le chat : le texte reste la voie de secours ultime.

Vérifié LIVE (serveur 8001, LLM réel) :
- « Donne-moi un exercice sur les fonctions Python » → `agent_response = {type: exercise, status: waiting_for_user, actions: [submit_answer, request_hint], data: {activity_id...}}` + `response` legacy intact.
- « Explique-moi les reseaux. » → `agent_response = {type: clarification, status: waiting_for_user, actions: [{select, options: [computer_networks, neural_networks]}]}`.

### B.5 Frontend (§27-§31) — zéro parsing de texte (§18)

Types (`types/agentResponse.ts`) : AgentResponse, AgentResponseStatus, AgentResponseType + data typées par type (ExerciseData, QuizData, CodeData, EvaluationData, HintData, SearchData, ClarificationData). ChatMessage et AgentEvent gagnent `agentResponse`/`agent_response`.

`components/agent/` (§28) — 10 composants :

| Composant | Rôle |
|---|---|
| `ResponseRenderer.tsx` | switch(response.type) — LE dispatcher ; type inconnu → texte (jamais de crash UI) |
| `TextResponse.tsx` | explication standard |
| `ExerciseCard.tsx` | exercice + boutons « ta réponse » / « un indice » |
| `QuizCard.tsx` | UNE question visible, progression i/N (barre) |
| `EvaluationCard.tsx` | feedback coloré par statut, score %, à-retravailler |
| `HintCard.tsx` | indice + niveau (points 1-3) |
| `CodeActivityCard.tsx` | réutilise le CodeEditor V5.2 existant (prop `initialCode` ajoutée, rétrocompatible) — pas de duplication |
| `SearchResultCard.tsx` | section Sources : title/source/url/snippet cliquables (§31) — jamais les scores |
| `ClarificationCard.tsx` | boutons select (§25) |
| `ErrorCard.tsx` | message propre, jamais de stack trace |

`MessageBubble` utilise le ResponseRenderer dès que `agentResponse` est présent (sinon affichage texte inchangé pour l'historique ancien). `ChatPage` câble les handlers : request_hint → message ; submit_answer → focus sur l'input (c'est la réponse de l'étudiant) ; select → « Je parle de X » (le bouton envoie, sans parsing).

UX §32 fallback : l'étudiant ne voit aucun détail technique ; les raisons de fallback, scores et budgets restent dans le Context Inspector (interface développeur).

### B.6 Tests — `tests/test_v67_output.py` : **30/30 PASS** (§34 + ADDENDUM §13)

Les 9 types convertibles, les 5 statuts publics acceptés, `success` refusé, type inventé refusé, les 10 mappings activity→response, sanitize §23 (zéro leak), §24 (SearchResult réutilisé, pas de 2e système), §25 boutons, §5 error propre, ADDENDUM §9 indépendance des couches, §26 sans LLM.

**Gates frontend §35 : `tsc -b` 0 erreur ; `vite build` ✓ (2.17s).**

---

## 35.G. Audit exhaustif des hardcodes (§62)

Audit par subagent dédié (grep systématique : `if subject ==`, `if model ==`, `if provider ==`, `== "python"`, `.includes(`, listes codées, chemins de fallback, constantes de scoring) sur backend/app/** + frontend/src/**, chaque ligne vérifiée en contexte.

### G.1 Verdict global

- **Zéro littéral de matière / modèle / provider dans une logique de décision.** Les 8 occurrences `== subject` backend sont des filtres paramétriques génériques (learning_profile/goals/activité courante). Les seuls textes « python » dans code_tools sont des docstrings documentant la règle §38.
- **Fallback V6.6 100% centralisé** : décision unique dans `app/context/fallback.py::decide_fallback` (appel unique builder.py), appliquée — jamais re-décidée — dans normalizer/prompt_builder/runner. Aucun if/elif de fallback local.
- **Frontend V6.7 conforme** : rendu par `response.type` (switch), défaut → texte, zéro parsing de message agent.

### G.2 Classification (42 findings)

| Classe | Total | Nature |
|---|---|---|
| [OK] | 20 | Filtres paramétriques, stoplists FR/EN génériques, parsing du protocole SSE/logs (pas du contenu agent), fallback centralisé, ResponseRenderer |
| [CONFIG] | 13 | Constantes documentées (W_TOPIC/RELEVANCE/WEB thresholds, `_OFFICIAL_DOMAINS` transverse), enums Pydantic Literal, contrats (RESPONSE_TYPE_*, FACT_CATEGORIES, unions TS), sandbox lists (`_BLOCKED_IMPORTS` sécurité réseau/système — aucune matière), config env |
| [LOGIC] | 7 | Décisions codées en dur à documenter/trancher — détail G.4 |
| [RISK] | 2 | Violations réelles mineures (frontend) — corrigées, voir G.3 |

### G.3 Les 2 [RISK] — MemoryPage.tsx (corrigés)

`MemoryPage.tsx` décidait la couleur des pastilles checkpoints en parsant le TEXTE du summary (`includes('Tool')`, `startsWith('User')`) — pas la réponse agent (le contrat §18 porte sur le rendu des réponses), mais le même anti-pattern. **Corrigé** : `_checkpoint_summary` du runner produit désormais un champ `kind` structuré (`user_message`/`tool_call`/`assistant`/`state`), exposé par l'API checkpoints et consommé par MemoryPage — plus aucun parsing de texte.

### G.4 Les [LOGIC] — décisions d'architecture consignées

| Localisation | Hardcode | Statut V6.8 |
|---|---|---|
| config.py `MODEL_NAME` | Défaut env `"qwen2.5"` | Le registry models.yaml devient la source déclarative des capacités ; config.py reste la source du nom du modèle ACTIF (env) — `get_model_capabilities()` applique l'env : jamais 3 sources contradictoires (§38) |
| pedagogical_tools.py:240 / code_tools.py:39 | « matière code » détectée par noms de tools (`execute_code`…) | Documenté : les tools spécialisés sont déclarés dans les YAML (`tools.specialized`) ; la garde sandbox vérifie l'appartenance déclarée, pas la matière |
| middleware.py MEMORY/LEARNING_TOOL_NAMES | Sets codés pour forçage user_id (sécurité §23) | Justifié : liste de sécurité fermée, stable ; documentée comme décision d'archi |
| taxonomy.py UNSUPPORTED_SUBJECTS | Alias de matières non supportées en Python (pas YAML) | Tranché : rôle = détection unsupported + anti-collision réseau/neuronal ; cohérent avec « pas de synonymes globaux » (aucun de ces alias n'injecte du routing supporté). Migration YAML possible plus tard — consigné |
| code_tools.py (2×) | Garde python-only du sandbox (`language in ("python","py","python3")`) | Décision d'archi mono-langage documentée inline (§5.2), consignée ici |

### G.5 Constantes [CONFIG] autorisées (inventaire)

Scoring knowledge (W_TOPIC 0.30…W_SUBJECT 0.10, seuil 0.3), scoring web (W_W_* 0.35…0.10, seuil 0.15), confiances router (0.95/0.85/0.80/0.55), `_OFFICIAL_DOMAINS` (transverse : doc/standards/édu — aucune matière), `_FORBIDDEN_DATA_KEYS` normalizer (§23 anti-fuite), stoplists ×5 (routing/knowledge/web/éval/mémoire — mots vides FR/EN génériques).

---

## 35.C. V6.8 — Context Budget + Model Capability Management (§36-§52)

### C.1 Model Capability Registry (§37-§39) — `app/models.yaml` + `app/context/model_capabilities.py`

Source déclarative unique des capacités, **valeurs réelles, rien d'inventé** :

```yaml
models:
  default:
    provider: ollama
    model: gemma4:31b-cloud
    context_window: null        # inconnue → fallback conservateur
    reserved_output_tokens: 2048
    supports_tools: true        # réel : l'agent appelle des tools
    supports_structured_output: false  # réel → chemin normalizer
    supports_vision: false
    supports_audio: false
```

API : `ModelCapabilities` (champs null si inconnu, §39), `get_model_capabilities(model_name|None)` (None → modèle actif de l'env via config.py — jamais 3 sources contradictoires §38 ; nom inconnu → capacités default clonées, sans invention), `supports(caps, "tools|structured_output|vision|audio")` (§49 — False → graceful fallback). Testable avec un YAML explicite (cross-model §14 : default + big-model 32000).

### C.2 Context Budget (§40-§48) — `app/context/budget.py`

- `estimate_tokens(text)` (§42) : heuristique documentée **≈4 chars/token** (`ceil(len/4)`), interface stable pour brancher un vrai tokenizer plus tard.
- `CONSERVATIVE_ASSUMED_WINDOW = 8192` (§40) : fenêtre ASSUMÉE quand elle est inconnue — le statut reste `unknown` pour signaler l'assomption ; `available_input_tokens` reste null dans le contrat (jamais une valeur inventée présentée comme réelle).
- **Priorités §41** : P0 system/message courant/activité (intouchables §43/§46) · P1 learning/subject · P2 knowledge/web · P3 mémoire · P4 thread.
- `apply_budget(sections, window, reserved)` — compression dans l'ordre §43 : drop P4 entiers → P3 (les moins pertinentes en dernier) → P2 web (top_k réduit, ordre de pertinence préservé §44) → statut final. **Exceeded ne crashe jamais** (§48) : on continue avec ce qui tient, P0 saufs.

| Statut §48 | Signification | Testé |
|---|---|---|
| ok | sous budget, marge saine | 5 |
| near_limit | ≥ 85% de l'available | 6 |
| compressed | une compression a suffi | 7a |
| exceeded | compression insuffisante (run continue, P0 intacts) | 7b |
| unknown | fenêtre inconnue (assomption conservatrice) | 14a/b |

### C.3 Intégration builder + ContextStats (§47) + preview

`build_context` construit les sections par priorité (learning P1, knowledge/web P2, mémoire P3, thread P4 — les P0 ne passent pas par le builder, intouchables par construction), applique le budget, reflète les drops (thread vidé, web réduit, mémoire tronquée) et remplit `ContextStats` étendu : `estimated_input_tokens, context_window, reserved_output_tokens, available_input_tokens, budget_status, sources_used, sources_dropped` — defaults pour ne casser aucun test existant. Event `CONTEXT_BUDGET` (vérifié live : status/est/window/sources/model).

`ContextPreviewResponse` gagne `budget` + `fallback` (contrat verrouillé, clés exactes) — **uniquement pour le Context Inspector** (§32/§55 : jamais dans le chat étudiant).

### C.4 Capability checks (§49-§51)

`supports(caps, "structured_output")` → false pour le modèle actif → chemin Response Normalizer (§50) ; vision/audio → false → graceful fallback (la vraie vision est une phase future §49). Le modèle et ses capacités sont de l'infrastructure (§51) : rien ne fuit dans le prompt — seul `model` apparaît dans les events/logs internes.

### C.5 Tests V6.8 (§52)

- `test_v68_models.py` : **8/8 PASS** — fenêtre connue (1), inconnue (2), structured output (12), tool calling (13), cross-model inconnu→default cloné (14a), registry réel honnête (15), YAML absent→defaults sûrs (16), null ≠ inventé (17).
- `test_v68_context_budget.py` : **17/17 PASS** — estimate (0a), réservé 29952 (3), conservateur (3b), calcul exact (4), sous budget (5), near_limit 91% (6), compressed P4 d'abord (7a), exceeded P0 saufs (7b/10/11), search réduite (8/8b), mémoire last-first (9), chemins capability (12-13), unknown (14a/b), builder réel sans crash + knowledge présent (15).
- `test_v68_final_integration.py` (§60) : **14/14 PASS** — voir D.

Vérifié LIVE : preview budget (258 tok, unknown, sources 2/0) + fallback (use_local_knowledge @ 0.95) ; chat réel « ordinateurs communiquent » → routing computer_networks → knowledge insufficient → web found → fallback use_web_search → AgentResponse text/completed. **Le pipeline complet §57 fonctionne réellement.**

---

## 35.D. Non-régression — résultats exacts (§53)

Suite de référence re-vérifiée AVANT toute modification (186/186), puis après l'intégration complète V6.6+V6.7+V6.8 :

| Suite | Fichier | Avant | Après |
|---|---|---|---|
| Architecture V5 | test_v5_architecture.py | 30/30 | **30/30** |
| Intégration V5 | test_v5_integration.py (serveur) | 10/10 | **10/10** |
| V5.2 unitaires | test_v52_unit.py | 58/58 | **58/58** |
| Architecture V6 | test_v6_learning.py | 35/35 | **35/35** |
| Intégration V6 | test_v6_integration.py (serveur) | 11/11 | **11/11** |
| E2E intégration | test_final_integration.py (serveur) | 19/19 | **19/19** |
| V6.5 search | test_v65_search.py | 23/23 | **23/23** |
| **V6.6 fallback** | test_v66_fallback.py | — | **22/22** |
| **V6.7 output** | test_v67_output.py | — | **30/30** |
| **V6.8 models** | test_v68_models.py | — | **8/8** |
| **V6.8 budget** | test_v68_context_budget.py | — | **17/17** |
| **§60 préparation** | test_v68_final_integration.py | — | **14/14** |

**Total : 186/186 existants (zéro suppression, zéro désactivation) + 91 nouveaux = 277/277 PASS.**

Gates frontend : `tsc -b` 0 erreur · `vite build` ✓ · `oxlint` 0 warning/0 erreur (13 fichiers dont les 10 nouveaux composants agent).

### D-bis. Test final §60 — préparation Learning Engine (14/14)

`test_v68_final_integration.py` prouve que TOUTES les informations du futur V7 sont disponibles dans un seul `BuiltContext` — **sans créer le Learning Engine** : User, Thread, Subject (python), Topic (confiance graduée), Knowledge (found), Search (structuré), Fallback (5 actions), Memory (liste honnête), Learning Profile (source de progression, §58), Activity (thread-local, séparée), Model capabilities (ollama/gemma4:31b-cloud, capacités honnêtes), Context budget (statut + estimation). Garde-fous vérifiés : le profil est une SOURCE (mastery/weak_points lisibles), AUCUN module learning engine n'existe (§59 : aucune décision pédagogique automatique).

---


Nouveautés V6.6–V6.8 en **gras** :

```text
backend/app/
  agent/   runner.py (§26 normalizer + kind checkpoint) response.py (V6.7)
           normalizer.py (V6.7) middleware.py (registre BuiltContext)
           state.py prompts.py tools.py memory.py pedagogical_tools.py
           code_tools.py activity_state.py learning_tools.py graph.py
  api/     schemas.py (ChatResponse.agent_response, CheckpointOut.kind,
           ContextPreviewResponse.budget/fallback) + 10 routes
  context/ fallback.py (V6.6) query_norm.py web_search.py (V6.5)
           schemas.py builder.py model_capabilities.py budget.py (V6.8)
           router.py prompt_builder.py knowledge_retriever.py
  learning/ learning_profile.py learning_context.py schemas.py (V6, source)
  subjects/ registry.py schema.py taxonomy.py tool_registry.py
            definitions/{python,biology,mathematics,computer_networks}.yaml
  knowledge/ 9 fichiers .md  |  models.yaml (V6.8)

backend/tests/ — 10 suites : v5_arch 30, v5_int 10, v52_unit 58,
  v6_learning 35, v6_int 11, v65_search 23, v66_fallback 22,
  v67_output 30, v68_models + v68_context_budget (V6.8),
  v68_final_integration (§60), final_integration 19 (E2E)

frontend/src/
  components/agent/ ResponseRenderer + TextResponse + ExerciseCard
    + QuizCard + EvaluationCard + HintCard + CodeActivityCard
    + SearchResultCard + ClarificationCard + ErrorCard (V6.7)
  components/chat/ MessageBubble (renderer si agentResponse)
    CodeEditor (initialCode) ChatInput (data-chat-input)
  components/memory/ ContextInspectorCard (Budget/Fallback §54)
  pages/ ChatPage (handlers actions) MemoryPage (kind §62)
  types/ agentResponse.ts agent.ts (agentResponse/kind)
  hooks/useChat.ts (agent_response du SSE)
```

---

## 35.F. Limitations honnêtes (§61-F)

1. **Tout reste lexical** (§40 maintenu) — pas d'embeddings ; la pertinence est un matching tokens/variantes ; une paraphrase non couverte par un alias YAML reste invisible au router.
2. **`supports_structured_output: false`** pour le modèle actif — c'est le normalizer (chemin 2 de §33) qui s'applique ; le chemin 1 (schema natif LLM) restera inutilisé tant qu'un modèle le supportant n'est pas configuré. Aucun impact : le contrat AgentResponse est produit de façon déterministe.
3. **estimate_tokens est une heuristique** (≈4 chars/token) — pas un tokenizer exact par modèle ; l'interface est stable pour brancher un vrai tokenizer plus tard (§42).
4. **Fenêtre de contexte du modèle actif inconnue** (cloud, non documentée côté projet) — le budget applique le fallback conservateur documenté ; les valeurs deviennent réelles dès que la fenêtre est configurée dans models.yaml.
5. **Le registre de contexte middleware est en mémoire process** (borné 128 threads) — le dernier run d'un thread gagne ; suffisant pour la normalisation (usage immédiat après le run), pas conçu pour de l'historique.
6. **Taxonomy UNSUPPORTED_SUBJECTS en Python** (pas YAML) — rôle anti-collision/détection unsupported ; migration YAML possible, consignée dans l'audit §G.4.
7. **Web search mono-source** (Ollama cloud) — unavailable/error → General Tutor proprement, mais pas de service alternatif (§41 : pas de nouveau provider).
8. **Le hint/quiz interactifs via AgentResponse.actions** reflètent l'activité réelle : si le LLM répond hors activité, la réponse est type=text — le mapping est fidèle à l'état, pas forcé.

---

## 35.E. Structure réelle du projet (§61-E)

Nouveautés V6.6–V6.8 en **gras** :

```text
backend/app/
  agent/   runner.py (normalizer + registre context + kind checkpoint)
           **response.py (V6.7 : AgentResponse, 5 statuts publics)**
           **normalizer.py (V6.7 : Response Normalizer §26)**
           middleware.py (registre BuiltContext par thread)
           state.py prompts.py tools.py memory.py pedagogical_tools.py
           code_tools.py activity_state.py learning_tools.py graph.py
  api/     schemas.py (ChatResponse.agent_response, CheckpointOut.kind,
           **ContextPreviewResponse.budget/fallback**) + 10 routes
  context/ **fallback.py (V6.6 : matrice §6 pure)**
           query_norm.py web_search.py (V6.5) schemas.py builder.py
           **model_capabilities.py + ../models.yaml (V6.8 registry)**
           **budget.py (V6.8 : ContextBudget/priorités/compression)**
           router.py prompt_builder.py knowledge_retriever.py
  learning/ learning_profile.py learning_context.py schemas.py (V6, source)
  subjects/ registry.py schema.py taxonomy.py tool_registry.py
            definitions/{python,biology,mathematics,computer_networks}.yaml
  knowledge/ 9 fichiers .md

backend/tests/ — 12 suites : v5_arch 30, v5_int 10, v52_unit 58,
  v6_learning 35, v6_int 11, v65_search 23, **v66_fallback 22**,
  **v67_output 30**, **v68_models 8**, **v68_context_budget 17**,
  **v68_final_integration 14 (§60)**, final_integration 19 (E2E)

frontend/src/
  components/agent/ **ResponseRenderer + TextResponse + ExerciseCard
    + QuizCard + EvaluationCard + HintCard + CodeActivityCard
    + SearchResultCard + ClarificationCard + ErrorCard (V6.7 §28)**
  components/chat/ MessageBubble (renderer si agentResponse)
    CodeEditor (initialCode) ChatInput (data-chat-input)
  components/memory/ ContextInspectorCard (**+Budget/Fallback §54**)
  pages/ ChatPage (handlers actions) MemoryPage (kind §62)
  types/ **agentResponse.ts (contrat V6.7)** agent.ts (agentResponse/
    kind/budget/fallback) hooks/useChat.ts (agent_response SSE)
```

---

## 35.X. Definition of Done finale (§66) — vérifiée

| Critère | Statut |
|---|---|
| V5 ✅ | 30/30 + 10/10 (§35.D) |
| V5.2 ✅ | 58/58 (§35.D) |
| V6 ✅ | 35/35 + 11/11 (§35.D) |
| V6.5 ✅ | 23/23 (§35.D) |
| V6.6 ✅ fallback centralisé + décision structurée + ambiguous/unknown/unsupported propres + knowledge insufficient distinct + web unavailable distinct + events + tests | §35.A — 22/22 |
| V6.7 ✅ AgentResponse + normalizer + zéro parsing frontend + 9 cartes + ResponseRenderer + tsc + vite | §35.B — 30/30 |
| V6.8 ✅ registry + budget + réservation output + priorités + préservation activité/message + budgets search/mémoire/learning + télémétrie + capability checks + fallback gracieux | §35.C — 25/25 + 14/14 |
| Aucune régression / aucun test supprimé ou désactivé | 186/186 intacts (§35.D) |
| Aucun système parallèle / RAG vectoriel / Learning Engine | audit §35.G + §35.F |
| ADDENDUM : 5 statuts publics exacts, success supprimé, Activity/Search/Router/Fallback/SSE indépendants | §35.B.1, tests contractuels |
| §60 toutes les infos V7 disponibles sans Engine | 14/14 (§35.D-bis) |

---

**Fin du rapport V6.6–V6.8.** Le socle est complet : Router → Retrieval (local + web) → Fallback Decision → Context Builder → Context Budget → Dynamic Prompt → LLM → Response Normalizer → AgentResponse → ResponseRenderer. Les 5 couches d'état (public/activité/search/routing/fallback) vivent leur vie séparée, chaque décision est testable sans LLM, le budget protège les P0, et le frontend rend la nature des réponses sans jamais parser de texte — **le projet est prêt pour V7 Learning Engine** sans devoir refaire le routing, la recherche, les fallbacks, le contexte ou le frontend.


