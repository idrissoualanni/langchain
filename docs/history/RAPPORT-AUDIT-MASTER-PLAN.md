# RAPPORT — AUDIT PHASE 0 : PLAN MASTER vs CODE RÉEL

> **Date** : 2026-09-19 — **Statut** : ✅ Terminé
> **Portée** : audit exhaustif du dépôt réel (`backend/` + `frontend/`) contre les
> 89 sections du plan `docs/plans/MASTER_IMPLEMENTATION_AGENT_TUTOR.md`.
> Aucune modification de code effectuée.

---

## 1. Exécutif

Le dépôt couvre déjà **~60 % du plan master**. Le socle (Main Graph, Learning
Engine, Activity, Memory, RAG documents, Tool Registry, Assistant UI) est en
place et testé. Il manque principalement les **subgraphs spécialisés**
(Problem, Coding, Research, Video), l'**Evaluation Engine déterministe**, et les
couches transverses **MCP, Guardrails, LiveKit, Admin**.

⚠️ **Écart critique au plan** : le plan (§1) affirme que des workflows « Problem
et Video déjà amorcés » existent (`problem_parse.py`, `problem_plan.py`,
`problem_validate.py`, `video_ingest.py`, `video_segment.py`). **Aucun de ces
fichiers n'existe dans le dépôt** (worktree, git `--all`). Ils devront être
créés, pas migrés.

---

## 2. Matrice Plan master → Réalité (cœur)

| § Plan | Sujet | État réel | Localisation / Écart |
|--------|-------|-----------|----------------------|
| §4 | Main Graph | ✅ Existant | `agent/graph.py` (`_compile_orchestration_graph`), `agent/orchestration.py` (7 nodes + `route_after_router`), `langgraph.json` → `build_graph` |
| §5 | Subgraphs spécialisés | ❌ Absents | aucun `graph/`, `subgraphs/` ; seul sous-graphe = `create_agent` (conversationnel) |
| §7 | Typed states | 🟡 Partiel | `CustomAgentState` (dict-based), `LearningActivityState` (TypedDict) ; pas de MainState/ProblemState/CodingState/ResearchState/VideoState |
| §8 | Subgraph contract | ❌ Absent | pas de `ProblemResult`/`CodingResult`/`ResearchResult`/`VideoResult` |
| §9-§11 | Tool architecture/registry/groupes | ✅ Solide | `tool_registry.py` (déclaré × implémenté, `resolve_tools`), `all_tools` = 26 tools en 6 groupes |
| §12 | Pedagogical tools | ✅ Solide | `pedagogical_tools.py` (1788 ln, 7 tools réels branchés sur knowledge base) |
| §13 | Memory tools | ✅ Solide | `memory.py` (875 ln) : profil + MemoryFacts v3 (7 catégories, recherche, déduplication) |
| §14-§17 | Activity system | 🟡 Partiel | machine à états V5.2 vivante (`activity_state.py`, `runner.py` register_activity, API activity) ; **pas de module `activity/` ni d'ActivityStore dédié** |
| §18-§20 | Evaluation Engine | ❌ Absent | `evaluate_answer` = tool LLM (pas de `EvaluationResult` déterministe : tests/lint/static/LLM) |
| §21 | Problem Subgraph | ❌ Absent | fichiers plan audités : introuvables |
| §22-§25 | Coding Subgraph | 🟡 Partiel | tools coding réels (`code_tools.py` 1083 ln, sandbox local `run_python_isolated` + `static_security_scan`), pas de subgraph |
| §24 | Code sandbox sécurité | 🟡 Existe local | `_sandbox_root()`, env nettoyé, timeouts (EXEC_TIMEOUT_S), purge ; **pas de sandbox de niveau production** (isolé/CPU/RAM/process par cgroup) |
| §26-§27 | Research Subgraph | ❌ Absent | recherche web V6.5 (`web_search.py`, `web_scraper.py`) mais pas de deep research/planner/claims |
| §28-§29 | Video Subgraph | ❌ Absent | introuvable |
| §30 | Document Subgraph | 🟡 Proche | RAG complet (`rag/`: chunker, documents, retriever, vector_store, schemas ; `document_tools.py` 4 tools ; API documents + ownership) — pas de workflow en subgraph |
| §31-§32 | Router V2 | 🟡 Partiel | router subject-only (`router.py`, `route_subject`) ; **pas de workflow-aware/intent/activity continuation** |
| §33 | Context Builder | ✅ Solide | `context/builder.py` + `retrieve_sources` ; 6 sous-services (web, semantic, budget, model_capabilities, tool_context, thread/user) |
| §34-§35 | Learning Engine | ✅ Complet | `learning/` (engine/decision/rules/schemas/context/profile) — moteur déterministe testé 40/40 |
| §39-§41 | MCP | ❌ Absent | aucun module MCP |
| §42-§47 | Guardrails | ❌ Absent | aucune couche `guardrails/` (input/tool/activity/learning/response) |
| §48-§50 | Admin | 🟡 Partiel | flags admin présents (`auth/resolver.py` `is_admin`, endpoints logs/ws admin-only) ; **pas de page/API admin dédiée** |
| §51-§60 | Frontend mapping/cards | 🟡 Partiel | Assistant UI présent ; ResponseRenderer + 9 cards ; pages Assistant/Documents/Logs/Memory/Profile + 10 pages learning + 7 settings ; pas de pages admin/research/video |
| §53 | Assistant UI | ✅ Présent | `frontend/src/assistant-ui/` (runtime Provider, tool-uis, types) |
| §61-§69 | Production hardening / observability | 🟡 Partiel | `logging/events.py` (log_event, event_bus, SSE, WS), LangSmith « app » ; **pas de `/ready`**, pas de retry policy LangGraph, pas d'idempotency générale |
| §70 | Store architecture | 🟡 Partiel | Checkpointer (SqliteSaver) + Store (SqliteStore) + RagStore + users/threads DB ; pas d'ActivityStore/ResearchStore |
| §71 | Knowledge ingestion | 🟡 Partiel | documents OK ; vidéos absentes |
| §75-§79 | Tests/évaluation | 🟡 Partiel | 19 suites tests ; pas de dataset de benchmarking ni perf tests |

---

## 3. Inventaire backend réel (`backend/app/`)

```
agent/           graph.py · orchestration.py · state.py · runner.py ·
                 middleware.py · normalizer.py · response.py · prompts.py ·
                 tools.py · pedagogical_tools.py (1788) · code_tools.py (1083) ·
                 memory.py (875) · learning_tools.py · document_tools.py ·
                 activity_state.py
api/             users · threads · chat · models · memory · logs · health ·
                 subjects · context · learning · activity · documents · schemas
auth/            resolver.py (Clerk + mode dev)
context/         builder · router · schemas · fallback · budget ·
                 model_capabilities · knowledge_retriever · web_search ·
                 web_scraper · prompt_builder · query_norm ·
                 tool_registry (compat) · semantic/ (provider, hybrid_ranker,
                 candidates, retriever, embedding_registry)
core/            exceptions.py
db/              connections · users · threads
knowledge/       17 matières (md), subjects/definitions/ + registry + taxonomy
learning/        engine · decision · rules · schemas · learning_context ·
                 learning_profile
logging/         events · sse
rag/             chunker · documents · retriever · vector_store · schemas
ws/              logs (websocket)
```

**Chaîne graph actuelle** : `START → router → retrieval → fallback → context →
learning → agent (create_agent) → response → END` avec conditionnel
`route_after_router` (supported/multi_domain → retrieval ; sinon → fallback).

---

## 4. Tools visibles par le LLM (26, `all_tools`)

| Groupe | Fichier | Tools |
|--------|---------|-------|
| recherche | `tools.py` | `recherche_web` (1) |
| memory | `tools.py` | get_user_profile, update_user_profile, get_user_memory, save_user_memory, update_user_memory, delete_user_memory, search_user_memory (7) |
| learning | `learning_tools.py` | get_learning_profile, get_learning_topic, record_learning_observation, update_learning_goal (4) |
| pédagogique | `pedagogical_tools.py` | create_exercise, evaluate_answer, give_hint, create_quiz, create_quiz_next, assess_understanding, propose_review (7) |
| coding | `code_tools.py` | execute_code, run_tests, analyze_code (3) |
| documents | `document_tools.py` | upload_document, search_documents, list_documents, delete_document (4) |

---

## 5. Sécurité / Auth

- **Auth** : Clerk production (`AUTH_MODE=clerk`, CLERK_ISSUER, JWKS, AUDIENCES,
  CLERK_SECRET_KEY) + mode dev (`dev:` users). Résolution JWT
  `auth/resolver.py`, guard admin `is_admin`.
- **Sandbox code** : exécution sous-processus isolé (env nettoyé, tmpdir,
  timeout, purge), scan statique (imports subprocess/os/sys interdits). Pas
  d'isolation lourde (cgroup/container) ni réseau par défaut à vérifier.
- **Logs** : interdits (clé, token, mots de passe, system prompt, mémoire
  privée). `/api/events` (SSE) + `/ws/logs` **ADMIN uniquement**.

---

## 6. Écarts prioritaires (à valider avant implémentation)

1. **Subgraphs manquants** : Problem, Coding, Research, Video, Document —
   le fichier cible du plan (`graph/subgraphs/*`) n'existe pas encore.
2. **Evaluation Engine** : pas de `EvaluationResult` déterministe (scoring,
   verdict, evidence, confidence) séparé du tool LLM `evaluate_answer`.
3. **Router V2** : workflow-aware + intent + activity continuation (aujourd'hui
   subject-only).
4. **MCP, Guardrails, LiveKit, Admin** : couches entièrement à créer.
5. **Typed states par subgraph** + contrats de sortie structurés.
6. **Production** : `/ready`, retries (transitoires), idempotency, timeouts
   systématiques, background jobs (video/research), migrations/backups.
7. **Fichiers « amorcés » du plan absents** (`problem_parse.py`, `video_*.py`).

---

## 7. Tests existants (backend/tests, 19 fichiers)

| Suite | Couverture (résultat vérifié récemment) |
|-------|------------------------------------------|
| test_v5_architecture | architecture/tools (31 refs) |
| test_v5_integration | intégration V5 |
| test_v52_unit | V5.2 pedagogiques (§43–§50 verts ; §51 cross-user = baseline Clerk) |
| test_v6_learning / test_v6_integration | profil learning + intégration (live LLM → quota 429) |
| test_v65_search / test_v66_fallback | recherche + fallback (live) |
| test_v67_output | AgentResponse 30 PASS |
| test_v68_context_budget / models / final | budget + models 10 PASS + final |
| test_v7_learning_engine | Learning Engine 40/40 PASS |
| test_v71_semantic | recherche sémantique hybrid (live) |
| test_v10_context_documents | documents/RAG 16/16 PASS |
| test_v11_document_web | documents+web 31 PASS |
| test_auth_security / test_clerk_jwt_leeway | auth Clerk |
| test_context_contracts / test_final_integration | contrats contexte + final (live) |

*Baseline déterministe verte : V7 40/40, V6.7 30, V6.8 models 10, V10 16/16,
V11 31, V5.2 §43–50. Suites live bloquées par quota Ollama cloud (HTTP 429) ce
jour.*

---

## 8. Versions installées

- `langchain` **1.4.2** — `create_agent` (langchain.agents) sous-graphe
  conversationnel.
- `langgraph` **1.2.11** — `StateGraph`, `SqliteSaver`, `SqliteStore`,
  checkpointer root à `backend/` (DB : checkpoints.db, long_term_memory.db).
- `langgraph-cli` **0.4.31** + `langgraph-api` **0.14.3** (entrypoint
  `langgraph.json` → `build_graph`).
- Python **3.14** (paquets dans `AppData\Roaming\Python\Python314`).
- Frontend : Vite + React + Tailwind v4 + Assistant UI (`frontend/src/assistant-ui`).

---

## 9. Recommandation d'ordre (référence plan §85)

1. **Phase 1** : Main Graph + typed states + contrats subgraphs (le socle existe :
   à standardiser, pas à recréer).
2. **Phase 2** : Activity + Evaluation Engine (combler §18-§20).
3. **Phase 3** : ProblemSubgraph (créer problem_parse/plan/validate).
4. **Phase 4** : CodingSubgraph + sandbox renforcé.
5. **Phase 6-7** : Research + Video subgraphs (respecter « hors chemin chat »).
6. **Phase 9** : MCP (Streamable HTTP).
7. **Phase 10** : Guardrails (créer seulement les modules justifiés).
8. **Phase 11-12** : LiveKit vertical slice.
9. **Phase 13** : Admin.
10. **Phase 15** : production hardening (health/ready, retries, timeouts,
    idempotency, background jobs).

*Rapport d'audit Phase 0 généré par l'assistant — chiffres et chemins issus du
code réel (globs/greps), aucune modification du dépôt.*