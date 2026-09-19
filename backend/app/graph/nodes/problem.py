# PROBLEM node du Main Graph — délègue au ProblemSubgraph (§21).
#
# Quand WORKFLOW_ROUTER décide "problem" (énoncé à résoudre pas à
# pas), CE node invoque le sous-graphe problem (PARSE → PLAN → GUIDE
# ↺ EVALUATE_STEP → VALIDATE → ARTIFACT) et persiste le ProblemResult
# (§8) dans workflow_result pour la chaîne suivante (CONTEXT → agent).
#
# Résolution "pas à pas" déterministe (parse/plan/guide/artefact).
# L'évaluation réelle d'une soumission reste déléguée au moteur §20 ;
# le sous-graphe ne contient AUCUN LLM. Le node rejoint ensuite la
# chaîne principale (comme ACTIVITY, §16).
from __future__ import annotations

from typing import Any

from app.graph.subgraphs.problem.nodes import compile_problem_subgraph
from app.logging.events import log_event

_compiled_problem = None


def _problem_subgraph():
    global _compiled_problem
    if _compiled_problem is None:
        _compiled_problem = compile_problem_subgraph()
    return _compiled_problem


def problem_node(state, config=None) -> dict[str, Any]:
    """PROBLEM — exécute le ProblemSubgraph pour l'énoncé courant.

    Entrée : l'énoncé vient du canal `intake.query` (ou du dernier
    message humain si absence). La soumission de l'étudiant vient du
    canal `submission` (évaluation d'étape contrôlée par l'agent).

    Sortie : invoque le sous-graphe compilé et récupère son
    `workflow_result` (ProblemResult §8). If le sous-graphe ne produit
    rien, on écrit un résultat partiel (non-régression).
    """
    intake = (state or {}).get("intake") or {}
    query = intake.get("query") if isinstance(intake, dict) else ""
    if not query and isinstance(state, dict):
        query = state.get("query") or ""

    submission = ""
    if isinstance(state, dict):
        submission = state.get("submission") or ""

    user_id = (state or {}).get("user_id") or ""
    thread_id = ""
    if config:
        thread_id = (config.get("configurable") or {}).get("thread_id") or ""

    sub = _problem_subgraph()
    result = sub.invoke(
        {
            "user_id": user_id,
            "thread_id": thread_id,
            "query": query,
            "statement": query,
            "submission": submission,
        }
    )

    workflow_result = result.get("workflow_result") or {}
    if not workflow_result:
        from app.graph.subgraphs.contracts import ProblemResult

        workflow_result = ProblemResult(
            workflow="problem",
            status="partial",
            message="Aucune résolution produite (énoncé vide ?)",
            verdict="mal_formule",
        ).model_dump()

    log_event(
        "PROBLEM_NODE",
        message=(
            f"Problem subgraph run | query_chars={len(query)} "
            f"| verdict={workflow_result.get('verdict')}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        extra={
            "operation": "problem_node",
            "verdict": workflow_result.get("verdict"),
            "status": workflow_result.get("status"),
        },
    )

    return {"workflow_result": workflow_result}


def route_after_problem(state) -> str:
    """Après PROBLEM : retour TOUJOURS sur la chaîne principale.

    La résolution a produit son ProblemResult ; le sous-graphe
    agentique rédige ensuite la réponse à partir de workflow_result
    (§18 : une seule évaluation, l'agent la rend).
    """
    return "context"


__all__ = ["problem_node", "route_after_problem"]