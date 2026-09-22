# MEMORY — Projet Agent Tutor (backend)

Checklist des modifications (une ligne par changement, format : `[tâche] → erreurs: [problème] → fix: [solution]`).

## Session refactor V10 (branch: refactor/architecture-v10 → master @ 71bbbb2)

- [infra technique → app/infrastructure/{database,sandbox,mcp,livekit,observability} + repositories] → erreurs: cycles d'import vs ancien layout → fix: shims de compatibilité temporaires (a7bf323)
- [tools LLM → app/tools/] → erreurs: anti-cycles → fix: 6 shims + agrégat all_tools (e1495d3)
- [domaines métier → app/services/] → erreurs: couplage app.agent → fix: façade memory + shims (3c2f064)
- [orchestration → app/services/agent/] → erreurs: — → fix: 5 shims (3229a0e)
- [Main Graph → app/graph/main/{graph,state,routing,edges}] → erreurs: — → fix: 4 shims (0a383f2)
- [contrats → app/schemas/workflow.py] → erreurs: — → fix: 13 shims (86f7bb2)
- [CodingSubgraph standardisé] → erreurs: state/logique mélangés → fix: state.py + nodes.py + compile_coding_subgraph (773a8b2)
- [DocumentSubgraph standardisé + node DOCUMENT → RAG réel] → erreurs: 2 tests fail (isolation RAG persistante sur disque) → fix: user_id unique par test + purge teardown ; validate_action fail-safe (§15) (5904fd0)
- [API/SSE/sécurité] → erreurs: ownership preview absent, erreurs brutes SSE, /ready toujours 200 → fix: get_current_user + 403/404, sanitize erreurs + WORKFLOW_RESULT streamé, /ready→503 (18628e6)
- [sandbox Windows + scan §24] → erreurs: 2 tests fail (preexec_fn UNIX-only, stub python3) → fix: preexec_fn conditionné, interpréteur par os.name, scan_code() pour tous types de tâche (1cf7bc8)
- [cleanup shims §30] → erreurs: imports résiduels app.agent.* dans production (middleware/orchestration/runner) + tests → fix: repointage vers services/graph ; suppression 36 modules ; create_coding_subgraph alias rendu canonique dans nodes.py ; langgraph.json → chemins canoniques + graphe document (4bb69d3)
- [second audit + fixes] → erreurs: test_model_gateway inspectait le mauvais module (retry_policy est dans edges.py register_nodes, plus compile_main_graph) ; test_phase2_activity sys.exit INTERNALERROR sous pytest ; post-invoke stream non ceinturé §47 ; AppError status HTTP figé 500 → fix: test adapté à register_nodes + graph_mod ; exclusion suites legacy non-régressives ; helper _yield_post_invoke_events + try/except gen() ; AppError.status_code par taxon ; suppression shim contracts.py ; purge pyc/dossiers résiduels ; docstrings legacy rafraîchies (71bbbb2)

## Notes opératoires

- Les scripts legacy de test autonomes (sys.exit) ne doivent PAS être exécutés sous pytest (INTERNALERROR) — `test_phase2_activity.py` (64/70, échecs préexistants §17 activity_log liés au node __activity_store__ obsolète), `test_phase2_evaluation.py`.
- Tests réseau (`test_auth_security.py`, `test_final_integration.py`) nécessitent un serveur local — exclus de la CI locale.
- Le binaire `tailscale-setup-*.exe` (app/livekit) n'est PAS tracké — ne jamais le committer.
- Dossiers frontend WIP utilisateur à NE JAMAIS committer : `frontend/src/components/assistant-ui/elements/thread.aui.tsx`, `frontend/src/pages/AssistantPage.tsx`, `frontend/src/hooks/use-composer-mentions.ts`.
- Piège bash Windows : backticks/parenthèses dans les messages de commit cassent le quoting → utiliser `git commit -F <fichier>`.
- Piège python : script hors du backend → sys.path ne contient pas `app` → PYTHONPATH=. obligatoire.
- RAG : `backend/database/user_documents.db` persiste sur disque — isolation tests par user_id unique + purge.