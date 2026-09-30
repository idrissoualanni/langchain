# Rapport final — Refactorisation d'architecture V10 (Backend Agent Tutor)

- **Date** : 2026-09-22
- **Branches** : `refactor/architecture-v10` → `master` (merge fast-forward, `71bbbb2`)
- **Périmètre** : backend `C:\Users\hp\Desktop\langchain\backend` (app, tests, langgraph.json, docs)

---

## 1. Bilan global

Refactorisation **structurellement saine et livrée** : l'architecture du backend est réorganisée,
tous les imports legacy sont supprimés, les 6 graphes compilent, et les suites de tests de référence
passent intégralement. Le merge sur `master` est un fast-forward strict (la branche de refactor partait
du HEAD exact de master, aucun commit divergent).

- `walk_packages` : **143 modules résolvables, 0 échec**
- Graphes `langgraph.json` : **6/6 compilent** (main 16 nodes, research 6, coding 7, video 7, problem 7, document 4)
- Tests de référence : **118/118 passés** (coding 20, document 7, model_knowledge_observability, v52, v11, research 21, model_gateway 30)
- Point d'entrée uvicorn `app.main:app` inchangé (nouveau layout)

## 2. Cible architecturale

| Avant | Après |
|---|---|
| `app/agent/*` (orchestration, middleware, prompts, runner, tools) | `app/services/agent/`, `app/tools/`, `app/graph/main/` |
| `app/db/*`, `app/livekit/*`, `app/mcp/*`, `app/observability/*`, `app/services/sandbox/*` | `app/infrastructure/{database,livekit,mcp,observability,sandbox}/` |
| Contrats workflows éparpillés (incl. shim `app/graph/subgraphs/contracts.py`) | Registre unique §8 : `app/schemas/workflow.py` |
| Subgraphs ad-hoc | `app/graph/subgraphs/{research,coding,video,problem,document}/nodes.py:compile_<x>_subgraph` |
| Imports croisés anciens chemins | **Zéro référence legacy** (vérifié par scan exhaustif app/ + tests/ + scripts/) |

---

## 3. Jalons livrés (commits)

| Commit | Contenu |
|---|---|
| `a7bf323` | Infra technique → `app/infrastructure/` + 24 shims ; repositories |
| `e1495d3` | Tools LLM → `app/tools/` (+6 shims, anti-cycles) |
| `3c2f064` | Domaines métier → `app/services/` + facade memory |
| `3229a0e` | Orchestration → `app/services/agent/` (+5 shims) |
| `0a383f2` | Main Graph → `app/graph/main/{graph,state,routing,edges}` (+4 shims) |
| `86f7bb2` | Contrats centralisés → `app/schemas/` (+13 shims) |
| `773a8b2` | CodingSubgraph standardisé (state.py + nodes.py + `compile_coding_subgraph`) |
| `5904fd0` | DocumentSubgraph standardisé + node DOCUMENT branché sur le RAG réel (7/7 tests) |
| `18628e6` | API/SSE/sécurité : ownership preview (403/404 anti-énumération), erreurs contrôlées, `WORKFLOW_RESULT` streamé |
| `1cf7bc8` | Sandbox exécution Windows + scan sécurité (§24) pour tous les types de tâche (67/67 tests) |
| `4bb69d3` | Cleanup des shims §30 : importeurs repointés, 36 modules supprimés, `langgraph.json` → chemins canoniques + graphe document |
| `71bbbb2` | Corrections du second audit : §30 clos, §47 double ceinturage SSE, §63 status HTTP par taxon, purge docstrings legacy |

---

## 4. Invariants métier vérifiés (second audit, `docs/history/RAPPORT-AUDIT-2-MASTER-PLAN.md`)

- **§8** — Un seul registre de contrats (`app/schemas/workflow.py`) ; les nodes du Main Graph adaptent les résultats subgraph vers le `WorkflowResult` public.
- **§13/§15** — 15 nodes du Main Graph assemblés (`graph.py`), edges et routing dans `edges.py`/`routing.py` ; `route_after_router` conforme (supported/multi_domain → retrieval, sinon fallback).
- **§24** — `scan_code()` exécuté pour **tous** les types de tâche avant exécution ; violation → `finalize_with_limit(security_violation)` ; verrous `__import__`/`importlib` exacts.
- **§30** — Suppression totale des shims `app/agent`, `app/db`, `app/livekit`, `app/mcp`, `app/observability`, `app/services/sandbox`, `app/graph/subgraphs/coding/graph.py`, `app/graph/subgraphs/contracts.py` ; **aucun import legacy** restant (scan `rg --pcre2` exhaustif, dont `__import__`/`importlib`).
- **§47** — SSE : identité uniquement via Bearer (anti-usurpation 403), erreurs sanitized (cause technique ∈ logs uniquement), événement `ERROR` garanti même en échec post-invoke (double ceinturage runner + `gen()` de chat.py).
- **§62** — `/ready` → HTTP 503 tant que non prêt.
- **§63** — Handler `AppError` → `{code, detail, error}` ; `status_code` désormais porté par le taxon (défaut 500, surchargeable) ; handler « dernier recours » sans stack leak.
- **Ownership** — preview context/subjects : `get_current_user` obligatoire, 403 cross-user, 404 anti-énumération, admin exempté ; `_validate_chat` : 403 usurpation, 404 thread absent, 403 thread étranger.

---

## 5. Points résiduels assumés (hors périmètre, documentés)

| Point | Nature | Décision |
|---|---|---|
| Cartes data-part frontend (`research-card`, `video-card`, `problem-artifact`) : shapes ≠ §8, aucun producteur backend | Dette de contrat §8, composants morts | **Option B assumée** : documenter comme legacy ; pas de casse runtime (workflow rép. `WORKFLOW_RESULT` émis côté backend, non encore consommé par le client) |
| `test_auth_security.py`, `test_final_integration.py` | Tests réseau nécessitant un serveur en cours | Hors périmètre CI locale ; préservés |
| `test_phase2_activity.py` / `test_phase2_evaluation.py` | Scripts legacy autonomes (`sys.exit`) avec échecs **préexistants** liés au design `__activity_store__` obsolète | Vérifié identique avant/après refactor (64/70) — non-régression |
| 3 fichiers frontend WIP (thread.aui.tsx, AssistantPage.tsx, use-composer-mentions.ts) | Travail utilisateur non commité | **Jamais commités ni inclus** ; stashed/restaurés autour du merge |

---

## 6. Préservation du travail utilisateur

Les 3 fichiers frontend en cours de modification ont été isolés par stash pendant le merge puis
restaurés intacts sur `refactor/architecture-v10`. **Aucun push effectué** — l'intégration reste locale ;
`origin/master` conserve son historique.

---

## 7. Commandes de validation (reproductibles)

```bash
# Compilation des modules
python -c "import pkgutil, importlib; ns='app'; [importlib.import_module(m.name) for m in pkgutil.walk_packages(importlib.import_module(ns).__path__, ns+'.')]"

# Graphes langgraph.json (importabilité + compilation)
PYTHONPATH=. python scripts/check_langgraph.py   # ou inline

# Suite de référence
python -m pytest tests/test_coding_subgraph.py tests/test_document_subgraph.py \
  tests/test_model_knowledge_observability.py tests/test_v52_unit.py \
  tests/test_v11_document_web.py tests/test_research_subgraph.py \
  tests/test_model_gateway_wiring.py -q
```