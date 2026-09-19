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

from langgraph.graph import END, START, StateGraph

from app.agent.orchestration import (
    context_node,
    fallback_node,
    learning_node,
    response_node,
    retrieval_node,
    route_after_router,
    router_node,
)
from app.graph.nodes import (
    activity_node,
    intake_node,
    problem_node,
    route_after_activity,
    route_after_problem,
    route_after_workflow_router,
    workflow_router_node,
)
from app.graph.state import MainState


def compile_main_graph(subgraph_agent, checkpointer, store):
    """Assemble et compile le Main Graph sur MainState.

    subgraph_agent : sous-graphe agentique (create_agent) — le
    sous-graphe conversationnel (§5) hérite checkpointer/store du
    graphe parent (POC-3).
    checkpointer   : persistance du thread state (SqliteSaver).
    store          : mémoire longue durée cross-thread.
    """
    graph = StateGraph(MainState)

    # --- Nodes du Main Graph (Phase 1/2) ---
    graph.add_node("intake", intake_node)
    graph.add_node("router", router_node)
    graph.add_node("retrieval", retrieval_node)
    graph.add_node("fallback", fallback_node)
    graph.add_node("workflow_router", workflow_router_node)
    graph.add_node("activity", activity_node)
    graph.add_node("problem", problem_node)
    graph.add_node("context", context_node)
    graph.add_node("learning", learning_node)
    graph.add_node("agent", subgraph_agent)
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
        # (ProblemSubgraph §21). Les subgraphs restants rempliront
        # ce mapping aux Phases 4-7.
        {"context": "context", "activity": "activity", "problem": "problem"},
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

    graph.add_edge("context", "learning")
    graph.add_edge("learning", "agent")
    graph.add_edge("agent", "response")
    graph.add_edge("response", END)

    return graph.compile(
        checkpointer=checkpointer,
        store=store,
    )


__all__ = ["compile_main_graph", "MainState"]