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
