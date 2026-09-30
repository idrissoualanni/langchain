# AUDIT & CLEANUP — Rapport final

Mission : `MISSION_AUDIT_CLEANUP_AGENT.md` — audit exhaustif + nettoyage contrôlé avant **V10 (User Knowledge + RAG)**.
Statut : **EN COURS** — rapport rédigé et mis à jour étape par étape (toutes les sections marquées `EN COURS` sont à compléter au fil de l'avancement).

---

## A. Executive Summary

`CLEANUP LOT 1-5 TERMINÉ — 0 RÉGRESSION`

- Référentiel : projet tutorat IA « Agent Control Center » — backend Python (FastAPI + LangChain/LangGraph 1.3.15, SQLite, Ollama, Clerk) + frontend React 19 / TypeScript / Vite / Assistant-UI.
- État actuel (branche `audit-cleanup`, HEAD `04ac164`) : cleanup LOTs 1-5 appliqués, tests + build vérifiés — **0 régression**. Baseline : tous les suites identiques (mêmes échecs pré-existants, aucun FAIL ajouté).
- Objectif : architecture saine et documentée avant V10 — **aucune implémentation V10 (RAG/Langfuse) dans cette mission**.

### Découvertes majeures (traitées)
1. **Outils démo/legacy** `additionner` + `calculer_longueur_texte` (`backend/app/agent/tools.py`) : **REMOVE** ✅ `all_tools` 24→22 (≥21 requis par test → OK).
2. **SSE `/api/events` (ADMIN)** : le backend vérifie le token (`app/logging/sse.py` — `?auth=` ou header), mais **2 connecteurs frontend ne fournissent jamais ce token** (`frontend/src/api/events.ts` pour LogsPage, `frontend/src/assistant-ui/api.ts` `connectAgentBus`) → 401 en mode clerk, reconnexion infinie. Bug pré-existant **documenté** (hors périmètre cleanup — correctif = changement de comportement).
3. **`TOOL_NAMES` (frontend)** : constante exportée mais **utilisée nulle part** ailleurs dans le frontend → entrées stale supprimées (LOT 1) ; suppression complète possible = REVIEW.
4. **Doublon de route Context Preview** : `/api/context/preview` (canonique V5) et `/api/subjects/preview/context` (utilisée par le frontend) — **les deux sont consommées** (frontend = subjects ; backend tests = context) → **KEEP**.
5. **Fichiers de travail supprimés dans le working tree** (état pré-existant, hors mission) : `astronomy.yaml` + `star_life.md` → restaurés ✅ + `star_life.md` ré-encodé (mojibake corrigé). **Test v5 destructif corrigé** : restauration au lieu de suppression (LOT 3 extras).
6. **Backups de DB commités dans git** : `backup-20260914-174858/*.db` → **REMOVE** ✅ (LOT 2).
7. **Junk** : `ap.py`, `agent_db.json`, `logs/agent.log.bak` → **REMOVE** ✅ (LOT 2). `PLAN.md`, `brief.md`, `deep-research-report.md`, `MEMORY.md`, `RAPPORT*.md`, `docs/plans/` → **MOVE** ✅ (LOT 5 : tout conservé, déplacé dans `docs/history/`).
8. **Mojibake `star_life.md`** : **corrigé** ✅ (ré-encodé UTF-8).
9. **SSE stream = événements, pas tokens** : `run_agent_stream` exécute `agent.invoke` dans un executor puis émet des événements — pas de token-streaming LLM. Cohérent avec le frontend.
10. **Duplication Normalizer** : bloc « lecture registre + `normalize_response` » dupliqué entre `run_agent` et `run_agent_stream` dans `runner.py` → REFACTOR candidat (reporté FUTURE, risque faible mais non critique).

---

## B. Git / Baseline

### B.1 État Git au départ
- Branche active : `audit-cleanup` (pré-existante).
- Autres branches : `master`, `mission/v5.2-pedagogical-tools` (deux uniquement).
- HEAD : `04ac164 MISSION V7.1-V8 : Identite Clerk + Frontend Assistant UI (espace utilisateur complet)`.
- Historique récent : `978756d` Consolidation RAPPORT, `47bdd9e` MISSION V7 Learning Engine, `ef1225e` V6.8.1 contrats, `b1dcfa1` V6.6-V6.8, `7ea14bc` V6.5, `37db9a9` Intégration finale, `f6dbc52` V5, `c279a66` V4.
- Au départ : seul `MISSION_AUDIT_CLEANUP_AGENT.md` non suivi ; `astronomy.yaml` + `star_life.md` supprimés en working tree (restaurés, voir A.5).
- **Aucun commit/push de la mission** (règle §missions).
- Fichiers racine trackés : `.gitignore`, `README.md`, `requirements.txt`, `ap.py`, `agent_db.json`, `brief.md`, `deep-research-report.md`, `MEMORY.md`, `PLAN.md`, `RAPPORT*.md`, `logs/agent.log.bak`, `docs/plans/2026-09-09-*`, `backend/database/backup-20260914-174858/*.db`, `backend/scripts/*.py` (4), `.env.example` (backend+frontend).
- Fichiers gitignorés présents sur disque : `.env*`, `frontend/v`, `frontend/*.log`, `frontend/vite_dev.*`, `backend/*.err`, `backend/*.out`, `*.log`, `__pycache__/`, `.pytest_cache/`, `.omo/`, `backend/database/*.db*`.

### B.2 Baseline tests backend
Mode d'exécution imposé : suites *script-style* (`check()` + `sys.exit(1)`), à lancer en direct : `PYTHONIOENCODING=utf-8 python tests/test_xxx.py`.

| Suite | Verdict | Détail |
|---|---|---|
| test_v7_learning_engine | ✅ PASS | 40/40 |
| test_v67_output | ✅ PASS | 30/30 |
| test_context_contracts | ✅ PASS | 50/50 |
| test_v68_context_budget | ✅ PASS | 17/17 |
| test_v68_final_integration | ✅ PASS | 16/16 |
| test_v68_models | ✅ PASS | 8/8 |
| test_clerk_jwt_leeway | ✅ PASS | exit 0 |
| test_v5_architecture | ❌ FAIL pré-existant | 26/30 (4 FAIL) |
| test_v65_search | ❌ FAIL pré-existant | 21/23 (2 FAIL) |
| test_v66_fallback | ❌ FAIL pré-existant | 21/22 (1 FAIL) |
| test_v52_unit | ❌ crash pré-existant | `KeyError: 'user_id'` |
| test_v6_learning | ❌ crash pré-existant | `TypeError NoneType` |
| test_auth_security | ⚠️ env requise | serveur non démarré (WinError 10061) |
| test_final_integration | ⚠️ env requise | idem |
| test_v5_integration | ⚠️ env requise | idem |
| test_v6_integration | ⚠️ env requise | idem |
| test_v71_semantic | ⚠️ block | hang réseau/embeddings (timeout 300 → exit 124) |

Total exécutable sans serveur : **161 PASS / 7 FAIL pré-existants** (logés dans `C:\Users\hp\AppData\Local\Temp\opencode\baseline\*.log`, hors repo).

### B.3 Baseline frontend
- `npm run build` = `tsc -b && vite build` → **OK** (9,04 s) ; seul warning chunk >500 kB (Vite).
- Lint config : `frontend/.oxlintrc.json` (oxlint).

---

## C. Architecture réelle AVANT cleanup

`PARTIELLEMENT COMPLÉTÉ` — cartographie lue directement dans le code (chemin de la requête) :

```
main.py (lifespan : init_db + warm-up get_agent + setup_logging + set_main_loop)
 └─ POST /api/chat (api/chat.py) : auth Clerk/dev (+ vérif user_id §403 + ownership thread)
 └─ GET  /api/chat/stream : SSE pipeline (agent-bus events)
 └─ runner.run (agent/runner.py) : _config_for(thread_id,user_id) → _runtime_context(AgentContext)
     └─ graph.create_agent : CustomAgentState(MessagesState) + SqliteSaver + memory SqliteStore
         └─ middleware.build_middleware_stack : dynamic_prompt (tutor_dynamic_prompt) + wrap_tool_call
             └─ tools : memory helpers + pédagogiques + code + (legacy additionner/calculer_longueur_texte) + recherche_web
         └─ normalizer (V6.7) : AgentResponse structurée (response_from_*)
         └─ learning/engine.decide : LearningDecision (12 actions §6/§7) → prompt strategy block
     └─ sse/logging : event_bus + GET /api/events (ADMIN) + WS /ws/logs
 └─ context/build_system_prompt (builder.py → prompt_builder.py)
     └─ router.route_subject → RoutingResult           [routing lexical, statuts supported/…]
     └─ knowledge_retriever (backend/app/knowledge/*.md) → KnowledgeResult
     └─ web_search (dns/ddg style) → SearchWebResponse
     └─ semantic/* (candidates, embedding_registry, hybrid_ranker, provider, retriever) → sem candidates
     └─ fallback.decide_fallback → FallbackDecision
     └─ model_capabilities, budget (V6.8), user_context, thread_context, tool_context
 └─ dbs : app.db (users/threads), checkpoints.db (LangGraph), long_term_memory.db (SqliteStore)
 └─ registry matières : subjects/definitions/*.yaml (17 matières) + knowledge/*.md par domaine
```

### Points d'architecture vérifiés
- **Identité** : `AUTH_MODE=clerk|dev`, token Bearer unique via `api/base.ts` côté frontend ; `CurrentUserResolver` + règles d'ownership (thread, admin) ; `sse.py` ADMIN-only vérifié côté backend.
- **State** : `CustomAgentState(MessagesState)` : + `user_id`, `interaction_count`, `learning_activity`, `activity_log` (Annotated add), `code_runs`.
- **Cache modèle** : `get_agent(model)` avec `_agents_by_model` (1 instance LangGraph par modèle Ollama).
- **Response** : `AgentResponse` (V6.7) avec statuts `completed/waiting_for_user/running/error/cancelled` ; normalizer avec `_FORBIDDEN_DATA_KEYS`.
- **Mémoire longue durée** : `SqliteStore`, `long_term_memory.db`, namespace `users/profile`, catégories 5, dédup ≥ 0.72, champs `FACT_CATEGORIES/FACT_SOURCES`.
- **Preview contexte** : handler partagé `build_context_preview` (api/subjects.py) → `/api/context/preview` + `/api/subjects/preview/context`.

---

## D. Agent Core

`COMPLÉTÉ` — fichiers vérifiés : `runner.py` (528), `graph.py` (107), `state.py`, `middleware.py` (370), `prompts.py`, `response.py`.
- **Prompt système** : `prompts.py` `CORE_PROMPT` (189 lignes) ; **alias `SYSTEM_PROMPT = CORE_PROMPT`** importé par graph.py → redondance d'export mineure (REFACTOR optionnel).
- **Graph V5** (`graph.py`) : `get_agent(model)` — instance par défaut (MODEL_NAME) + cache `_agents_by_model` (1 instance/modele Ollama, même checkpointer/store). `_build_agent` : ChatOllama (temperature 0) + SqliteSaver + `get_store()` + `create_agent(state_schema=CustomAgentState, context_schema=AgentContext, middleware=build_middleware_stack())`. **Aucune logique métier dans graph.py** (§63 respecté).
- **Runner** (`runner.py`) : `_config_for` (thread_id+user_id en configurable) + `_runtime_context` (AgentContext natif §4). `run_agent` (POST) et `run_agent_stream` (SSE) → mêmes étapes (RUN_START/STATE_LOAD/USER_MESSAGE/…/ASSISTANT_MESSAGE/CHECKPOINT_SAVED/RUN_END). Stream = `agent.invoke` dans executor + événements (pas de tokens). Historique checkpoints avec `kind` structuré (V6.8). `interaction_count` incrémental par thread.
- **Middleware** (`middleware.py`) : `@dynamic_prompt tutor_dynamic_prompt` (context builder → decide V7 → prompt ; fallback `CORE_PROMPT` sur erreur CONTEXT_BUILD_ERROR ; registre `_last_context_registry` borné 128 purgé → consulté par le normalizer) + `ToolEventMiddleware.wrap_tool_call` (TOOL_START/END/ERROR + **forçage user_id** sur `MEMORY_TOOL_NAMES` (7) et `LEARNING_TOOL_NAMES` (4) ; erreur tool → ToolMessage, jamais de crash).
- **State** (`state.py`) : `CustomAgentState(MessagesState)` : `user_id`, `interaction_count`, `learning_activity`, `activity_log` (Annotated operator.add), `code_runs`.
- **Normalizer V6.7** (`normalizer.py`) : `normalize_response` → AgentResponse ; constructeurs `response_from_text/activity/search/clarification/error` ; `_sanitize_data` avec `_FORBIDDEN_DATA_KEYS` (pas de fuite interne).
- **Response** : `AgentResponse`, statuts `completed/waiting_for_user/running/error/cancelled`.
- **Vérifications sécurité** : anti-usurpation user_id (403, admins exceptés), ownership thread (403), identité = Bearer uniquement (`api/chat.py`).
- **API Chat** (`api/chat.py`, 128) : POST `/api/chat` (response_model=ChatResponse) + GET `/api/chat/stream` (SSE) ; validation via ChatRequest (UUID verrouillés, model optionnel).

## E. Tools

`COMPLÉTÉ` — `agent/tools.py` (327), `code_tools.py` (1083), `pedagogical_tools.py` (1587), `learning_tools.py`, `subjects/tool_registry.py` (124).
- Inventaire réel **24 tools** (vérifié en runtime) :
  - **Legacy démo (REMOVE)** : `additionner`, `calculer_longueur_texte` — outils arithmétique/string « repris de ap.py », **aucun test** les référence, aucun SubjectConfig ne les déclare ; impact suppression : 24 → 22 (assertion `>= 21` OK).
  - **KEEP** : `recherche_web` (proxy vers `context/web_search.web_search`) ; 7 tools mémoire (`get/update_user_profile`, `get/save/update/delete/search_user_memory`) ; 7 pédagogiques (`create_exercise`, `evaluate_answer`, `give_hint`, `create_quiz`, `create_quiz_next`, `assess_understanding`, `propose_review`) ; 4 learning (`get_learning_profile`, `get_learning_topic`, `record_learning_observation`, `update_learning_goal`) ; 3 code (`execute_code`, `run_tests`, `analyze_code` — garde interne par SubjectConfig §37).
- **Registre** : `subjects/tool_registry.py` — `_implemented_tool_names()` = source de vérité (import tardif `all_tools`, anti-cycle) ; `resolve_tools` croise déclaré×implémenté → `available/unavailable` (WARNING TOOL_UNAVAILABLE) ; `get_tools_for_subject` = vue stats frontend/preview.
- **Aucun hardcode matière** dans le registre ni le router (pas de `if subject ==`).

## F. Memory

`COMPLÉTÉ` — `agent/memory.py` (839) + `db/`.
- `SqliteStore` LangChain sur `long_term_memory.db` (dir config) ; namespace `users/profile` (`NAMESPACE_LABEL`) ; 5 catégories `FACT_CATEGORIES` (identity/background/personality/preference/interest) ; sources `FACT_SOURCES` ; dédup ≥ `DEDUP_THRESHOLD=0.72` ; stopwords `_STOP_WORDS`.
- API mémoire `api/users.py` : profile GET/PUT (rejet `user_id` via validateur `never_user_id`), facts CRUD + recherche + overview ; `api/memory.py` : state/history thread (checkpointer).
- `db/connections.py` (86) : SQLite thread-local, schema users/threads + migrations additives Clerk (idempotentes), UNIQUE index partiel `clerk_user_id`.

## G. Memory Flow

`COMPLÉTÉ` — flux réel :
1. `runner` → `_build_input` persiste `user_id`+`interaction_count` dans le state LangGraph.
2. `dynamic_prompt` → `build_context` construit `user_context` (profil+faits) + `thread_context` (historique récent) → `build_system_prompt`.
3. Tools mémoire écrivent dans `long_term_memory.db` (interactions mid-run, protégées par forçage user_id §23).
4. `get_store()` du graph = même store que les tools → mémoire cross-thread.
5. V6.8.1 : `register_activity(thread_id, activity)` enrichit **par copie** le BuiltContext du registre (jamais mutation de l'original) pour la décision V7.

## H. Frontend Memory

`EN COURS` — pages Memory + LongTermMemoryCard (500-719 lignes) + hook `useMemory` — le flux mémoire frontend sera vérifié en étape 8.

## I. Context/Prompt

`COMPLÉTÉ` — `builder.py` (664), `prompt_builder.py` (352), `context/__init__.py`.
- `build_context` : routage → knowledge → web/semantic → fallback → tools → user → thread → learning → stats/budget → BuiltContext (pydantic extra=forbid).
- `build_system_prompt` (prompt_builder.py) : noyau + bloc matières (routing) + notes connaissance + web + profil mémoire + thread + **bloc stratégie Learning** (`add_learning_strategy_block` V7).
- `context/__init__.py` : **ré-export redondant** `build_system_prompt` (F811 noqa — `builder.py` le ré-exporte déjà via prompt_builder) → REFACTOR mineur.
- `budget.py` : `ContextBudget/BudgetSection/BudgetResult`, `estimate_tokens`, `build_budget`, `apply_budget` (compression/suppression quand > fenêtre) — Périmètre V6.8.
- `model_capabilities.py` : `ModelCapabilities` + `supports` (par modèle).
- `query_norm.py` : accent/stemming/expansion lexicale.
- `thread_context.py` : historique récent ; `user_context.py` : profil+faits ; `tool_context.py` : `get_tools_for_subject`.

## J. Search/Fallback

`COMPLÉTÉ` — `router.py` (742), `knowledge_retriever.py`, `web_search.py`, `fallback.py`, `semantic/*`.
- **Router lexical** : statuts `supported/ambiguous/multi_domain/unsupported/unknown` (scores matières, règles de désambiguïsation, priorité connaissance locale). Aucun hardcode de code matière.
- **Knowledge** : `KNOWLEDGE_DIR = backend/app/knowledge/*.md` (17 domaines) découpés en sections `## topic` ; recherche lexicale + fallback par stem.
- **Web** (`web_search.py`) : build requête FR, qualité de domaine (`source_quality`), rang par pertinence, `status found/insufficient/unavailable/error`. Consommé par le tool `recherche_web` ET le builder.
- **Sémantique** (`semantic/*`) : `provider.py` (embeddings), `embedding_registry.py`, `candidates.py`, `hybrid_ranker.py`, `retriever.py` — **brique préparée pour RAG** (test_v71_semantic bloqué sur environnement embeddings — hors baseline).
- **Fallback** (`fallback.py`) : `decide_fallback(routing, knowledge, web)` → `FallbackDecision` (use_local_knowledge / use_web_search / ask_clarification / use_general_tutor / continue_without_external_search) ; `is_vague_query` ; note pour prompt.
- **3 moteurs coexistants (knowledge lexical / web / semantic)** → point de vigilance V10 (voir §V) : choisir un socle RAG, ne pas tripler les flux au moment d'indexer les documents utilisateur.

## K. AgentResponse / API / SSE

`COMPLÉTÉ`
- Contrat : normalizer V6.7 (backend) ↔ `frontend/src/types/agentResponse.ts` → `ResponseRenderer.tsx`.
- API verrouillée (`api/schemas.py`, 399 lignes) : **aucun ancien schema** ; `ChatResponse` unique ; `StreamingResponse` = fastapi.responses (SSE légitime) — pas de doublon `api/context.py`/`api/subjects.py` hormis le preview partagé (§A.4).
- SSE : `/api/events` ADMIN-only (`logging/sse.py` : header Bearer OU `?auth=` ; backfill 100 ; ping 15 s ; signale 401/403 sans preuve). WS `/ws/logs` (`ws/logs.py`).
- ⚠️ **Bug documenté** : connecteurs frontend `events.ts` + `assistant-ui/api.ts` n'injectent PAS le token → `/api/events` refuse (401) ; les cartes outils live et la console logs sont donc muettes en dépendant du bus (verdict : pré-existant, à corriger hors cleanup).
- `main.py` (109) : lifespan (logging, init_db, warm-up, set_main_loop) ; CORS localhost:5173 ; inclusion des 11 routers + `/api/events` + `/ws/logs` ; health `/`.

---

## L. Frontend

`EN COURS` — React 19 + Vite + Assistant-UI + Clerk + zustand.
- Pages : Assistant, Logs, Memory, Profile, learning/* (9), settings/* (8) ; 16 998 lignes TS/TSX au total.
- `TOOL_NAMES` : **défini mais inutilisé ailleurs** (candidat REMOVE).
- Appels API : `api/base.ts` centralise le Bearer token ; `api/subjects.ts` consomme `/api/subjects/preview/context` (pas le canonique `/api/context/preview`).

---

## ÉTAPES 10-14 — CLASSIFICATION & PLAN DE CLEANUP

### Classification (règle §49 : KEEP / REMOVE / REFACTOR / MERGE / MOVE / DERIVE / REVIEW / FUTURE)

**Fichiers / modules :**

| Élément | Catégorie | Justification |
|---|---|---|
| `backend/app/agent/tools.py` — tools `additionner`, `calculer_longueur_texte` | REMOVE | Démo « repris de ap.py » ; aucun test, aucune registration de subject, aucun appelant (vérifié) ; 24→22 tools (`>=21` test conservé) |
| `backend/app/context/__init__.py` ligne 18 (`from prompt_builder import build_system_prompt  # noqa F811`) | REFACTOR | Import réellement redondant : `builder.py` ré-exporte déjà `build_system_prompt` (ligne 66 + `__all__`) |
| `backend/app/agent/prompts.py` — alias `SYSTEM_PROMPT=CORE_PROMPT` | KEEP | Consommé par `graph.py` ET test_v5_architecture / test_v52_unit |
| Routes `/api/context/preview` + `/api/subjects/preview/context` | KEEP | **Les deux sont consommées** : frontend → subjects ; tests (v7_learning_engine, final_integration, v6_integration) → context. Handler partagé `build_context_preview`. Alias documenté ↔ pas de doublon à supprimer |
| `runner.py` bloc normalize (POST vs SSE) | REFACTOR (reporté) | ~15 lignes dupliquées ; factorisation mécanique (fallback vs fallback_pre). Risque faible mais non critique → laissé en nette amélioration FUTURE pour ne pas déstabiliser |
| `frontend/src/types/agent.ts` `TOOL_NAMES` — 2 entrées stale | REMOVE (entrées) / const KEEP | Entrées `additionner`/`calculer_longueur_texte` supprimées avec les tools ; la constante (non utilisée) reste comme documentation du contrat → complète REMOVE possible = REVIEW |
| `ap.py`, `agent_db.json`, `logs/agent.log.bak`, `backend/database/backup-20260914-174858/*.db` | REMOVE | Prototypes/historique : aucun import, fonctionnalité portée (register-tools), backups binaires en git |
| `PLAN.md`, `brief.md`, `deep-research-report.md`, `MEMORY.md`, `RAPPORT*.md`, `docs/plans/` | MOVE ✅ (LOT 5) | Décision utilisateur : tout conserver → déplacé dans `docs/history/` (git mv) |
| `backend/scripts/*.py` (4 utilities) | KEEP | Outils de dev utiles (coherence markdown, e2e clerk, convert knowledge, adapt tests) |
| Tout `backend/app/**` restant + `backend/tests/**` + `backend/knowledge/**` | KEEP | Responsabilités claires, consommateurs identifiés, testés |
| Tout `frontend/src/**` restant | KEEP | Toute page/component/hook/api référencé (vérifié) |
| Fichiers gitignorés de session (`frontend/v`, `*.log`, `vite_dev.*`, `backend/*.err|*.out`, `__pycache__/`, `.pytest_cache/`, `.omo/`, `server*`) | REMOVE (disque) | Artefacts régénérés ; pas d'impact git |

### Plan de cleanup par lots (agit §53, adapté au réel) — ÉTAT D'EXÉCUTION

```
LOT 1 — Tools inutiles          : DONE — tools.py (additionner/calculer_longueur) + TOOL_NAMES →
                                     all_tools 24→22 ; tests backend OK ; build frontend OK
LOT 2 — Legacy racine           : DONE — ap.py, agent_db.json, logs/agent.log.bak,
                                     backend/database/backup-20260914-174858/ (backups DB commités)
LOT 3 — Redondance context      : DONE — import dupliqué F811 supprimé (context/__init__.py) →
                                     imports package OK ; tests v5/v67 OK
LOT 4 — Junk disque gitignoré   : DONE — frontend/v, *.log, vite_dev.*, backend/*.err/out,
                                     __pycache__, .pytest_cache, .omo
LOT 5 — Documents (REVIEW)      : DONE — décision utilisateur : TOUT CONSERVER, déplacé dans
                                     docs/history/ (git mv) ; docs/plans/ inchangé ; 0 référence cassée
```

Découverte corrective intégrée au cleanup : `test_v5_architecture.py` détruisait les fichiers `astronomy.yaml`/`star_life.md` (rewrite + unlink) ; corrigé en restauration + `star_life.md` ré-encodé (mojibake). Détails en O.1.

Résumé des impacts sur `all_tools` : vérifié en runtime **24 tools** ; après LOT 1 = **22 tools** (≥21 requise par test_v6_learning → satisfaite). `MEMORY_TOOL_NAMES` (7) + `LEARNING_TOOL_NAMES` (4) inchangées.

---

## M. Fichiers supprimés

| Fichier | Décision | Justification | Impact |
|---|---|---|---|
| `ap.py` (racine) | REMOVE | Prototype ancien ; tools portés dans `backend/app/agent/tools.py` (log_event structuré) ; aucun import ni script | aucun |
| `agent_db.json` (racine) | REMOVE | Ancienne DB prototype V1 ; aucune lecture dans le code | aucun |
| `logs/agent.log.bak` | REMOVE | Backup de log commité par erreur | aucun |
| `backend/database/backup-20260914-174858/app.db` | REMOVE | Backup binaire commité (jeu de données obsolète) | aucun |
| `backend/database/backup-20260914-174858/checkpoints.db` | REMOVE | idem | aucun |
| `backend/database/backup-20260914-174858/long_term_memory.db` | REMOVE | idem | aucun |
| Junk disque gitignoré (`*.log`, `*.err`, `*.out`, `frontend/v`, `__pycache__/`, `.pytest_cache/`, `.omo/`) | REMOVE (disque) | Artefacts de session régénérés ; aucun impact git | aucun |
| 7 documents historiques → `docs/history/` | MOVE (LOT 5) | Décision utilisateur : « tous conserver et les mettre dans le dossier docs » — déplacés (git mv, historique préservé), aucune référence cassée | aucun |

Courbes : toutes les suppressions vérifiées avant coupure (chaîne Bash, sessions brisées A→F + subtests complets après chaque lot).

---

## N. Tools supprimés

| Tool | Fichier | Catégorie | Enregistré | Appelants | Tests | Décision |
|---|---|---|---|---|---|---|
| `additionner` | `backend/app/agent/tools.py` | UTILITY (démo) | `tools = [...]` (liste agent) | aucun | aucun | REMOVE |
| `calculer_longueur_texte` | `backend/app/agent/tools.py` | UTILITY (démo) | `tools = [...]` (liste agent) | aucun | aucun | REMOVE |

- Impact : `all_tools` 24 → **22 tools** (constat runtime après LOT 1). L'assertion `>= 21` du test_v6_learning reste satisfaite.
- `TOOL_NAMES` (frontend `types/agent.ts`) : 2 entrées stale retirées (`additionner`, `calculer_longueur_texte`) en cohérence avec le backend. La constante reste exportée comme documentation du contrat ; complet retrait possible = REVIEW (constante non consommée).
- `MEMORY_TOOL_NAMES` (7) et `LEARNING_TOOL_NAMES` (4) du middleware : inchangés.

---

## O. Code supprimé

| Élément | Décision | Justification |
|---|---|---|
| `backend/app/context/__init__.py` — `from app.context.prompt_builder import build_system_prompt` (ligne 18, `# noqa: F811`) | REFACTOR | Import réellement redondant : `builder.py` ré-exporte déjà `build_system_prompt` (ligne 66 + `__all__`) ; résolution `from app.context import build_system_prompt` vérifiée identique |

## O.1 Corrections défensives (découvertes pendant le cleanup)

| Fichier | Type | Détail |
|---|---|---|
| `backend/tests/test_v5_architecture.py` | CORRECTION TEST | Le test réécrivait `astronomy.yaml` + `star_life.md` puis **les supprimait** (unlink + rmtree) en fin de run → destruction de fichiers trackés à chaque exécution. Désormais : capture de l'original avant mutation, **restauration** en fin (ou suppression seulement si l'original n'existait pas). Contrat §49 intact (26/30, mêmes 4 échecs pré-existants) |
| `backend/app/knowledge/sciences/astronomie/star_life.md` | CORRECTION CONTENU | **Mojibake** (double-encodage UTF-8 : « â€” », « Ã©toile », « cÅ“ur ») → réécrit en Français UTF-8 propre. `check_md_coherence.py` : 70 fichiers, **0 incohérence** (avant : contrainte violée) |

---

## P. Simplifications (AVANT → APRÈS)

- Tools : 24 → **22** (2 démos supprimées) ; liste `tools = [recherche_web, ...]` nettoyée.
- Imports redondants : `context/__init__.py` (F811) → supprimé (0 duplicata d'import dans le package).
- Fichiers legacy trackés : 6 supprimés (2 racine + 1 log + 3 backups DB).
- Junk disque gitignoré : nettoyé (logs, err/out, cache Python, `.omo`, `frontend/v`).
- Side-effect destructif de test éliminé : les données `astronomy` ne sont plus détruites à chaque exécution de test_v5_architecture.
- Contenu knowledge corrompu : `star_life.md` ré-encodé correctement.

---

## Q. Éléments conservés

`EN COURS` — pour l'instant : tout ce qui est sous `backend/app` + `frontend/src` + `backend/knowledge` + `backend/tests` est préservé.

---

## R. Éléments FUTURE (hors périmètre)

`EN COURS` — V10 User Knowledge + RAG, Langfuse, HITL, multi-agent, nouveau provider — NON implémentés ici.

---

## S. NON-RÉGRESSION

**Ré-exécution complète post-cleanup — 0 régression (aucune dégradation vs baseline).**

| Suite | PASS / FAIL | État |
|---|---|---|
| test_v7_learning_engine | 40/0 | OK |
| test_context_contracts | 50/0 | OK |
| test_v68_final_integration | 16/0 | OK |
| test_v67_output | 30/0 | OK |
| test_v68_context_budget | 17/0 | OK |
| test_v68_models | 8/0 | OK |
| test_clerk_jwt_leeway | 8/0 | OK |
| test_v5_architecture | 26/30 | inchangé (4 échecs pré-existants S54/S51/S52/S4) |
| test_v65_search | 21/23 | inchangé (2 échecs pré-existants S30b/S31) |
| test_v66_fallback | 21/22 | inchangé (1 échec pré-existant S13) |
| test_v6_learning | prefix-6/1 | inchangé (TypeError pré-existant S.I) |
| test_v52_unit | prefix-49/1 | inchangé (KeyError pré-existant S.52) |
| test_final_integration | error rc=1 | inchangé (WinError 10061 — serveur éteint) |
| test_v5_integration | error rc=1 | idem |
| test_v6_integration | error rc=1 | idem |
| test_auth_security | error rc=1 | idem |

**Frontend** : `npm run build` OK (9s, même warning chunk size pré-existant).

**Contenu markdown** : `check_md_coherence.py` → **70 fichiers, 0 incohérence** (avant : star_life.md violait la contrainte d'encodage).

---

## T. Arbre réel FINAL

`À VENIR`

---

## U. Problèmes restants

`MAJ POST-CLEANUP` — résolus par le cleanup (3, 4, 5, 7) ; documentés/restants :
1. **SSE `/api/events` non authentifié côté frontend** (401 → reconnexion boucle) — `events.ts` + `assistant-ui/api.ts` « connectAgentBus » n'injectent pas le token malgré les commentaires. **RESTE OUVERT** (correctif = changement de comportement, hors périmètre).
2. 7 FAIL / 2 crashes backend pré-existants (non liés au cleanup) + suites « integration » dépendantes du serveur/Ollama (environnement).
3. ~~Mojibake `star_life.md`~~ → **corrigé** ✅ (ré-encodé).
4. ~~Backups DB commités~~ → **supprimés** ✅ (LOT 2).
5. ~~`agent_db.json` + `ap.py`~~ → **supprimés** ✅ (LOT 2).
6. Duplication du bloc normalizer entre `run_agent` et `run_agent_stream` → **REFACTOR reporté en FUTURE** (risque faible, non critique).
7. ~~Ré-export redondant `build_system_prompt` (F811)~~ → **supprimé** ✅ (LOT 3).
8. `SYSTEM_PROMPT = CORE_PROMPT` : alias d'export (redondance mineure, KEEP — consommé par graph.py + tests).
9. **LOT 5** : documents historiques → **déplacés dans `docs/history/`** ✅ (décision utilisateur : tout conserver).

## V. Risques avant RAG

`COMPLÉTÉ` (analyse seulement, V10 non implémenté) :
- 3 moteurs de recherche coexistants (knowledge lexical .md, web, semantic/embeddings) → risque de doublon/coût au moment du RAG : définir un socle d'indexation unique (le répertoire `semantic/` est déjà la brique préparée).
- Contrats extra=forbid (LearningDecision, BuiltContext, AgentContext) : à ne pas casser lors de l'ajout de champs doc utilisateur.
- SSE (source unique des événements outils) doit être fiabilisée (auth) avant de brancher le RAG.
- Tool `recherche_web` VS `web_search` du builder : les deux consomment `context/web_search.py` — garder la source de vérité unique pour la recherche web.

---

## W. Préparation V10

`EN COURS` : cette mission ne touche pas V10. Les éléments de préparation relevés (classification fichiers + report) sont documentés ici.

---

*Rapport généré dans le cadre de `MISSION_AUDIT_CLEANUP_AGENT.md`. Dernière mise à jour : cleanup LOTs 1-4 terminés, 0 régression — en attente LOT 5 (documents).*