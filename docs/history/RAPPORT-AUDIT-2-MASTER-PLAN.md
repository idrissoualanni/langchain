# Rapport — Second Audit Global (Mission §17) — Backend Agent Tutor

- **Date** : 2026-09-22
- **Branche** : `refactor/architecture-v10`
- **Périmètre** : READ-ONLY — `backend/` (app, tests, scripts), `langgraph.json`, `docs/plans/MASTER_IMPLEMENTATION_AGENT_TUTOR.md`, `frontend/src` (consommation API)
- **Référence** : `docs/plans/MASTER_IMPLEMENTATION_AGENT_TUTOR.md` (§8, §13, §15, §24, §30, §47, §62, §63)
- **Aucune modification de fichier, aucun commit.**

---

## 0. Résumé exécutif

La refactorisation est **structurellement saine** : aucune import runtime réel vers les anciens chemins (`app.agent.*`, `app.db.*`, `app.livekit.*`, `app.mcp.*`, `app.observability.*`, `app.services.sandbox.*`, `app.graph.subgraphs.coding.graph`) ne subsiste dans le code de production. Les invariants §8/§13/§15/§24/§47/§62/§63 sont vérifiés. Les 6 graphes de `langgraph.json` pointent vers les nouveaux emplacements. Les 67 tests de référence passent et les 143 modules se résolvent.

**1 problème haut, 3 problèmes moyens, 3 constats bas**, détaillés ci-dessous.

---

## 1. (a) Problèmes trouvés

### 🔴 HAUT — Import legacy réel restant dans les tests

**`tests/test_model_gateway_wiring.py:250`**
```python
def test_graph_uses_retry_policy_on_agent_node(self):
    ...
    from app.agent import runner      # ← import d'un package SUPPRIMÉ
```
- Le package `app.agent` n'existe plus (ni `app/agent/`, ni `app/agent.py`).
- Ce test n'est **ni skippé ni marqué** ; son exécution déclenche `ModuleNotFoundError: No module named 'app.agent'` (erreur de test, pas échec silencieux).
- `tests/test_model_gateway_wiring.py` n'appartient **pas** à la liste des 67 tests validés (test_coding_subgraph, test_document_subgraph, test_model_knowledge_observability, test_v52_unit, test_v11_document_web) — il a échappé au tri.
- → **Violation directe du §30** (« aucun fichier ne doit plus référencer app.agent.* »).
- **Correction suggérée** : remplacer par l'import depuis `app.services.agent.runner` (l'entité `runner` vit désormais dans `app/services/agent/`).

---

### 🟠 MOYEN — Shim de compatibilité §30 non supprimé

**`app/graph/subgraphs/contracts.py`** (33 lignes)
- Le fichier est explicitement déclaré *« SHIM de compatibilité … SUPPRESSION prévue phase cleanup (§30) »* (docstring lignes 1-4) et re-exporte uniquement depuis `app/schemas/workflow.py`.
- Il n'est consommé **que** par `tests/test_research_subgraph.py:25` (`from app.graph.subgraphs import contracts as subgraph_contracts`) et référencé en docstring par `app/graph/subgraphs/research/__init__.py:8`.
- Le §30 (« suppression des shims ») n'est donc **pas entièrement clos** : si le test `test_research_subgraph` est migré vers `app.schemas.workflow`, le fichier devient supprimable.

---

### 🟠 MOYEN — Incohérences de contrat §8 vs consommateurs data-part (frontend)

Les cartes `data part` du frontend suivent **un schéma plus ancien** que le registre §8 (`app/schemas/workflow.py`), et **aucun producteur backend ne les injecte** :

| Data part frontend (`frontend/src/components/chat/cards/`) | Champs attendus | Contrat §8 backend (`app/schemas/workflow.py`) | Écart |
|---|---|---|---|
| `research-card.tsx` → `ResearchResult` | `{query, summary, sources[{url,title,snippet,relevance}], status, confidence}` | `ResearchResult` (l.161) : `{plan, claims, summary}` + `status: JobStatus` | `query`, `sources`, `confidence` absents ; `claims` jamais consommé ; `JobStatus`(`ok|error|partial|skipped`) ≠ statut UI (`completed\|in_progress\|failed`) |
| `video-card.tsx` → `VideoContent` | `{title, duration, thumbnail_url, segments[{start_time,end_time,text,topic}], status}` | `VideoResult` (l.181) : `{video_id, transcript, segments[{title,summary,start,end,topics}], knowledge_keys}` | Shape `segments` différente ; `title/duration/thumbnail_url/transcript` manquants ; statuts incompatibles |
| `problem-artifact.tsx` → `ProblemSolution` | `{problem_statement, subject, steps[{step_number,description,user_answer,is_correct,feedback}], final_solution, rigor_score(0-100), status}` | `ProblemResult` (l.99) : `{understanding, solution_steps, verdict, confidence(0-1), markdown}` | `steps ≠ solution_steps` ; `rigor_score ≠ confidence` ; `problem_statement`, `subject`, `final_solution` absents |

Constat complémentaire :
- Aucun producteur de `ResearchResult`, `VideoContent`, `ProblemSolution` (au sens frontend) dans `backend/app/` (cherché via `rg` dans `app/`).
- Le SSE `WORKFLOW_RESULT` émis par `app/services/agent/runner.py` **n'est pas consommé** : le client `frontend/src/assistant-ui/api.ts` ne traite que `ASSISTANT_MESSAGE`, `TOOL_START/END/ERROR`, `ERROR` et les événements Activités.

→ Pas de casse visible au runtime (les cartes sont des composants morts), mais **dette de contrat §8 réelle** : soit documenter ces cartes comme legacy, soit connecter un producteur `WORKFLOW_RESULT` + adapter les shapes, soit supprimer les cartes.

---

### 🟠 MOYEN — Handler §63 : HTTP 500 systématique pour toutes les AppError

`app/main.py` — handler global (l.~160-175) :
```python
except AppError as exc:
    return JSONResponse(status_code=500, content={"code":…, "detail":…, "error":…})
```
- ✅ Le **shape** `{code, detail, error}` est conforme au §63.
- ❌ Le **code HTTP est figé à 500** quelle que soit la nature de l'erreur (`validation`, `authorization`, `not_found` devraient être 4xx). `app/core/exceptions.py` ne porte pas de code HTTP distinct de la taxonomie.
- La taxonomie du master §63 distingue ces familles ; renvoyer un 500 pour une erreur autorisation/not_found dégrade la précision HTTP côté clients et outils d'autopsie.
- → Recommandation : faire dépendre le status HTTP du taxon `AppError`.

---

### 🟡 BAS — Dossiers résiduels + `__pycache__` d'anciens modules

- `app/db/__pycache__/` contient encore des `.pyc` compilés des anciens modules déplacés : `connections`, `threads`, `users` (compilés cpython-312 **et** cpython-314).
- `app/mcp/servers/__pycache__/` : `.pyc` de `calendar_server`, `filesystem_server`.
- `app/observability/` : dossier vide (uniquement `__pycache__`).
- 👉 **Aucun impact runtime** (pas d'`__init__.py` → non importables ; le scan `walk_packages` des 143 modules passe), mais :
  - les `.pyc` périmés peuvent tromper les outils de static analysis qui scannent les caches ;
  - la présence de dossiers vides évoque de faux modules « encore supprimables ».
- → Nettoyage cosmétique de la phase cleanup (§30).

---

### 🟡 BAS — Documentation/comments référençant les anciens chemins (périmée, aucun impact runtime)

- `app/config.py:163`, `app/config.py:193`
- `app/graph/main/graph.py:174` (`app.agent.memory.get_store`)
- `app/graph/nodes/__init__.py:5`
- `app/api/livekit.py:132`, `app/api/livekit.py:311`
- `app/repositories/users.py:1`, `app/repositories/threads.py:1`, `app/repositories/__init__.py:7`
- `app/services/context/builder.py:9`
- `app/services/memory/memory.py:164`
- `app/services/models/resolver.py:195`, `app/services/models/resolver.py:201`
- `frontend/src/assistant-ui/api.ts:198` (`app/agent/pedagogical_tools.py`)

---

### 🟡 BAS — §47 : trou de sanitization en fin de run stream

`app/services/agent/runner.py` — dans `run_agent_stream` :
- ✅ Le `try/except` encadrant `invoke_llm_with_retry` convertit correctement toute erreur LLM en événement `{"event": "ERROR", …}` avec message **générique** (cause réelle ∈ logs) — pas d'exception brute exposée au client.
- ❌ Les opérations **post-invoke** (`agent.get_state(config)`, `normalize_response`, `log_event`, sérialisation du checkpointer) sont **hors** de ce `try`. Si l'une d'elles lève pendant le stream, le générateur côté `app/api/chat.py` (fonction `gen()`) n'a pas non plus de `try/except` → la connexion SSE se coupe net, **sans événement `ERROR`** envoyé, contrairement au §47.
- → Recommandation : englober le run complet (invoke **+** post-traitement) dans le bloc de sanitization, et/ou ceinturer `gen()` dans `app/api/chat.py`.

---

## 2. (b) Points vérifiés OK

### §30 — Absence d'imports legacy (cœur de la mission)
- Recherche exhaustive `rg --pcre2 '^\s*(from|import)\s+app\.(agent|db|livekit|mcp|observability)|…app\.services\.sandbox|…coding\.graph'` sur `app/`, `tests/`, `scripts/` → **un seul hit** : `tests/test_model_gateway_wiring.py:250` (voir problème haut).
- Les hits restants sont des **commentaires/docstrings** (cf. constat bas) — aucun exécutable.
- `__import__` / `importlib.import_module` : seuls usages = `app/infrastructure/sandbox/executor.py:76-77` (verrou exact `"__import__"`, `"importlib"`) et `tests/test_v6_learning.py:396` (chemin **nouveau** `app.services.learning.learning_engine`) — aucun ne référence un chemin legacy.

### §3 / §5 — Compilation & points d'entrée
- `langgraph.json` : **6 graphes** tous sur les nouveaux chemins — `app/graph/main/graph.py:build_graph` + `app/graph/subgraphs/{research,coding,video,problem,document}/nodes.py:compile_<x>_subgraph`.
- Chaque paquet subgraph expose `compile_<x>_subgraph` dans son `__init__.py` (`app/graph/subgraphs/{coding,research,video,problem,document}/__init__.py`), `app/graph/main/__init__.py` exporte `build_graph`/`compile_main_graph`/`get_agent`.
- Les 6 graphes compilent ; la marche `walk_packages` = 143 modules OK ; 67/67 tests de référence OK.
- Point d'entrée uvicorn `app.main:app` inchangé (nouveau layout).

### §8 — Contrat des workflows (subgraphs ↔ graphe parent)
- Registre source unique dans `app/schemas/workflow.py` : `SubgraphResult` + 5 résultats (`ResearchResult`, `CodingResult`, `ProblemResult`, `VideoResult`, `DocumentResult`) + `JobStatus`, `SubgraphInput`, `KNOWN_WORKFLOWS`, registry `SUBGRAPH_RESULTS`.
- Nodes du Main Graph (`app/graph/nodes/{research,coding,problem,video,document}.py`) délèguent aux subgraphs et **adaptent** les résultats internes vers le contrat §8 (ex. `CodingResult` interne → `WorkflowResult` §8) ; les subgraphs produisent leurs propres types internes.
- `payload` (entrée structurée §8/SubgraphInput) : présent dans `MainState` (`app/graph/main/state.py:117`), parsé et transmis jusqu'au run.

### §13 / §15 — Nodes, edges, routing du Main Graph
- `app/graph/main/graph.py` : assembly des 15 nodes attendus (intake, router, retrieval, fallback, workflow_router, activity, problem, research, coding, video, document, context, learning, agent, response).
- `app/graph/main/edges.py` : `register_nodes` / `register_edges` / `register_workflow_branches` structurés.
- `app/graph/main/routing.py` : table workflow → node + `SUBGRAPH_RETURN`/`WORKFLOW_BRANCHES`.
- Node ROUTER : `app/services/agent/orchestration.py:90` → `route_subject`, résultat persisté en `routing_result`.
- Routing conditionnel §15 : `orchestration.py:294-304` — `route_after_router` renvoie `"retrieval"` si `status ∈ {supported, multi_domain}`, sinon `"fallback"` (ambiguous/unknown/unsupported) ✔ conforme au §15.
- Nœuds ACTIVITY/PROBLEM/RESEARCH/CODING/VIDEO/DOCUMENT = délégation aux subgraphs ; CONTEXT → `build_context` ; LEARNING → `decide` ; RESPONSE → `normalize_response` (source de vérité unique §48).

### §24 — Scan avant exécution du code (sandbox)
- `app/graph/subgraphs/coding/nodes.py` → `execute_action` : `scan_code(state.get("code") or "")` appelé **en premier** pour **tous** les types de tâche (debug/test/write/edit/explain).
- `app/infrastructure/sandbox/executor.py:76-77` : verrous exacts `"__import__"` / `"importlib"`.
- Limite documentée : le scan ne porte que sur le champ `state["code"]`, pas sur le prompt/comments du user — conforme au périmètre §24.

### §47 — SSE : identité, sanitization, isolation
- `app/api/chat.py` : `GET /api/chat/stream` — identité **uniquement** via header `Authorization` (Bearer), `user_id` en query est une *vérification* anti-usurpation (403 si ≠ session) ; `payload` JSON invalide → ignoré + tracé (jamais 400 bloquant) ; framing SSE `event:` + `data:` propre ; headers `Cache-Control: no-cache`, `X-Accel-Buffering: no`.
- `run_agent` (POST /api/chat) : catch large → HTTP 500 contrôle (message générique, jamais stack leak) ✔.
- Isolation mémoire utilisateur : `app/services/agent/middleware.py` — `ToolEventMiddleware.wrap_tool_call` **force** `user_id` depuis le Runtime Context (défense en profondeur ; le §36 interdit d'injecter la valeur réelle du user_id dans les prompts), lecture mémoire sélectionnée par Runtime Context.

### §62 — Healthcheck
- `app/api/health.py` : `/ready` renvoie **503 tant que `ready` est faux** (et 200 une fois prêt) ; `agent_ok` et `langgraph_ok` codés en dur `True` (état synthétique documenté).

### §63 — Handlers d'exception globaux
- `app/main.py` : `AppError → {code, detail, error}` (shape conforme) ; handler « dernier recours » capturant les exceptions non gérées ; **pas de stack leak vers le client**.

### Ownership & anti-énumération (preview context / subjects)
- `app/api/context.py` : `Depends(get_current_user)` obligatoire ; délègue à `build_context_preview`.
- `app/api/subjects.py` → `build_context_preview` : non-admin + `user_id` cible ≠ courant → `get_user(payload.user_id)` ; target inexistant → **404** (message unique « Utilisateur introuvable ») ; sinon **403** — anti-énumération OK.
- `app/api/chat.py` `_validate_chat` : user_id du body ≠ session → 403 ; thread absent → 404 ; thread non `thread_belongs_to_user` → 403.

### Structure des nouveaux emplacements
- `app/infrastructure/{database,livekit,mcp,observability,sandbox}/` présents ; `app/services/agent/` (prompts, middleware, normalizer, runner, orchestration) câblé partout ; `app/tools/` ; contrats §8 dans `app/schemas/workflow.py`.

---

## 3. (c) Incohérences de contrat §8 — synthèse actionnable

| Élément | Statut |
|---|---|
| Registre §8 backend (source unique) | ✅ Cohérent en interne (nodes adaptent tous les résultats subgraph vers `WorkflowResult` §8) |
| Consommation via SSE `WORKFLOW_RESULT` | ⚠️ Émis par le runner mais **non traité** par le client frontend (`assistant-ui/api.ts`) |
| Cartes data-part `ResearchResult` / `VideoContent` / `ProblemSolution` | ⚠️ **Composants morts** : aucun producteur backend, shapes ≠ §8 (voir tableau problème moyen) |
| Statuts (`JobStatus` backend vs statuts UI frontend) | ⚠️ Vocabulaires incompatibles (`ok/error/partial/skipped` vs `completed/in_progress/failed`) |

**Décision recommandée (à trancher) :**
1. *Option A — aligner* : injecter un producteur `WORKFLOW_RESULT` côté SSE, brancher le frontend dessus, et remapper les shapes des cartes sur le §8.
2. *Option B — assumer legacy* : marquer/supprimer les 3 cartes data-part et documenter qu'elles n'existent plus dans le contrat §8.
3. Dans les deux cas : autoriser `test_research_subgraph` à importer depuis `app.schemas.workflow` pour pouvoir supprimer le shim `app/graph/subgraphs/contracts.py`.

---

## 4. Prochaines étapes suggérées (hors périmètre READ-ONLY)

1. Corriger `tests/test_model_gateway_wiring.py:250` (import `app.agent` → `app.services.agent.runner`).
2. Migrer `tests/test_research_subgraph.py:25` vers `app.schemas.workflow` puis **supprimer** `app/graph/subgraphs/contracts.py` (clôture réelle du §30).
3. Purger les `.pyc` et dossiers résiduels (`app/db/`, `app/mcp/servers/`, `app/observability/`).
4. Ceinturer le post-traitement de `run_agent_stream` (et `gen()` de `app/api/chat.py`) dans le bloc de sanitization §47.
5. Faire dépendre le status HTTP du taxon `AppError` (status 4xx pour validation/authorization/not_found).
6. Rafraîchir les commentaires/docstrings listés (constat bas).
7. Trancher l'option A ou B pour les cartes data-part (incohérence §8 ↑).