# Main Graph (Phase 1) — assemblage standardisé du graphe (§4/§83).
#
# Phase 1 : STANDARDISER, pas recréer. compile_main_graph assemble
# les nodes métier existants (app.agent.orchestration — source de
# vérité unique §48) avec les DEUX nouveaux nodes d'orchestration
# propres au Main Graph (INTAKE, WORKFLOW_ROUTER) sur le schéma typé
# MainState. Le sous-graphe agentique (create_agent), le checkpointer
# et le store restent fournis par l'appelant (app/agent/graph.py).
#
# Graphe du Main Graph (Phase 2) :
#
#   START → INTAKE → ROUTER ──(supported/multi_domain)→ RETRIEVAL
#                        │                            │
#                        └─(ambiguous/...)→ FALLBACK  │
#                                              │      │
#                              RETRIEVAL ───────┘      │
#                                │                     │
#                                └──────────→ FALLBACK←┘
#                                                │
#                                                ▼
#                                         WORKFLOW_ROUTER ──(main)→ CONTEXT
#                                                │
#                                                ├─(activity)→ ACTIVITY ─→ CONTEXT
#                                                └─(subgraphs Phases 3-7)
#                                                │
#                                                ▼
#                                      CONTEXT → LEARNING → AGENT → RESPONSE → END
#
# WORKFLOW_ROUTER est le point d'insertion des future subgraphs (§88)
# : chaque Phase spécialisée câblera sa branche dans
# WIRED_WORKFLOWS + graphe.add_node/edges.
from __future__ import annotations

import inspect

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from app.agent.orchestration import (
    context_node,
    fallback_node,
    learning_node,
    response_node,
    retrieval_node,
    route_after_router,
    router_node,
)
from app.config import (
    AGENT_RECURSION_LIMIT,
    MODEL_RETRY_ATTEMPTS,
)
from app.graph.nodes import (
    activity_node,
    coding_node,
    document_node,
    intake_node,
    problem_node,
    research_node,
    route_after_activity,
    route_after_coding,
    route_after_document,
    route_after_problem,
    route_after_research_node,
    route_after_video,
    route_after_workflow_router,
    video_node,
    workflow_router_node,
)
from app.graph.state import MainState
from app.models.retry import is_transient_error


def compile_main_graph(subgraph_agent, checkpointer, store):
    """Assemble et compile le Main Graph sur MainState.

    subgraph_agent : sous-graphe agentique (create_agent) — le
    sous-graphe conversationnel (§5) hérite checkpointer/store du
    graphe parent (POC-3).
    checkpointer   : persistance du thread state (SqliteSaver).
    store          : mémoire longue durée cross-thread.

    Limites (mission §3, lues depuis app/config.py — jamais de
    valeur hardcodée ici) :
      - node AGENT : retry policé borné (retry_policy, max_attempts
        configurables, UNIQUEMENT sur erreurs transitoires via
        is_transient_error)
      - timeout : PAS passé au node (timeout= n'est supporté par
        LangGraph que pour les nodes ASYNC ; le node agent est sync).
        Il est ENFORCÉ par le runner (I/O boundary) via wait_for
        (AGENT_TIMEOUT_SECONDS dans invoke_llm_with_retry).
      - recursion_limit : passé au compile quand la version de
        LangGraph le supporte ; il est TOUJOURS appliqué par la
        config d'invocation du runner (point d'application réel).
    """
    agent_retry_policy = RetryPolicy(
        initial_interval=0.5,
        backoff_factor=2.0,
        max_interval=4.0,
        max_attempts=MODEL_RETRY_ATTEMPTS,
        jitter=True,
        retry_on=is_transient_error,
    )

    graph = StateGraph(MainState)

    # --- Nodes du Main Graph (Phase 1/2) ---
    graph.add_node("intake", intake_node)
    graph.add_node("router", router_node)
    graph.add_node("retrieval", retrieval_node)
    graph.add_node("fallback", fallback_node)
    graph.add_node("workflow_router", workflow_router_node)
    graph.add_node("activity", activity_node)
    graph.add_node("problem", problem_node)
    graph.add_node("research", research_node)
    graph.add_node("coding", coding_node)
    graph.add_node("video", video_node)
    graph.add_node("document", document_node)
    graph.add_node("context", context_node)
    graph.add_node("learning", learning_node)
    graph.add_node(
        "agent",
        subgraph_agent,
        retry_policy=agent_retry_policy,
    )
    graph.add_node("response", response_node)

    # --- Arêtes ---
    graph.add_edge(START, "intake")
    graph.add_edge("intake", "router")

    graph.add_conditional_edges(
        "router",
        route_after_router,
        {"retrieval": "retrieval", "fallback": "fallback"},
    )
    graph.add_edge("retrieval", "fallback")
    graph.add_edge("fallback", "workflow_router")

    graph.add_conditional_edges(
        "workflow_router",
        route_after_workflow_router,
        # Phase 2 : "main" → context, "activity" → node ACTIVITY
        # (continuation §16). Phase 3 : "problem" → node PROBLEM
        # (ProblemSubgraph §21). Phases 4-7 : research (§26), coding
        # (§22), video (§28), document (§30) — WIRED_WORKFLOWS est
        # COMPLET : tout workflow connu a une branche réelle.
        {
            "context": "context",
            "activity": "activity",
            "problem": "problem",
            "research": "research",
            "coding": "coding",
            "video": "video",
            "document": "document",
        },
    )

    # ACTIVITY (continuation) rejoint toujours la chaîne principale :
    # l'évaluation/indice se fait dans le sous-graphe agentique (tools
    # V5.2), le node ACTIVITY ne fait qu'enregistrer le contrat §8.
    graph.add_conditional_edges(
        "activity",
        route_after_activity,
        {"context": "context"},
    )

    # PROBLEM (résolution d'énoncé) rejoint aussi la chaîne principale
    # : le ProblemSubgraph produit le ProblemResult §8 dans
    # workflow_result, le sous-graphe agentique rédige la réponse.
    graph.add_conditional_edges(
        "problem",
        route_after_problem,
        {"context": "context"},
    )

    # RESEARCH / CODING / VIDEO / DOCUMENT : même pattern — le subgraph
    # produit son résultat §8 dans workflow_result, puis revient sur la
    # chaîne principale (CONTEXT → LEARNING → AGENT → RESPONSE).
    graph.add_conditional_edges(
        "research",
        route_after_research_node,
        {"context": "context"},
    )
    graph.add_conditional_edges(
        "coding",
        route_after_coding,
        {"context": "context"},
    )
    graph.add_conditional_edges(
        "video",
        route_after_video,
        {"context": "context"},
    )
    graph.add_conditional_edges(
        "document",
        route_after_document,
        {"context": "context"},
    )

    graph.add_edge("context", "learning")
    graph.add_edge("learning", "agent")
    graph.add_edge("agent", "response")
    graph.add_edge("response", END)

    compile_kwargs: dict = {"checkpointer": checkpointer, "store": store}
    if "recursion_limit" in inspect.signature(StateGraph.compile).parameters:
        compile_kwargs["recursion_limit"] = AGENT_RECURSION_LIMIT

    return graph.compile(**compile_kwargs)


__all__ = ["compile_main_graph", "MainState"]