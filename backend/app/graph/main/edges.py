# Main Graph Edges — enregistrement nodes + arêtes (§26 mission refactor).
#
# Découpé depuis app/graph/main.py : compile_main_graph ne fait plus
# qu'orchestrer register_nodes / register_edges /
# register_workflow_branches puis compiler. Les fonctions de routage
# (route_after_*) restent avec leurs nodes (app/graph/nodes/ pour
# l'orchestration, app/agent/orchestration.py pour le métier — source
# de vérité unique §48, migrée vers services/agent/ en tâche 5/7).
from __future__ import annotations

from langgraph.graph import END, START

from app.services.agent.orchestration import (
    context_node,
    fallback_node,
    learning_node,
    response_node,
    retrieval_node,
    route_after_router,
    router_node,
)
from app.graph.main.routing import SUBGRAPH_RETURN, WORKFLOW_BRANCHES
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


def register_nodes(graph, subgraph_agent, agent_retry_policy=None) -> None:
    """Déclare les 15 nodes du Main Graph.

    subgraph_agent : sous-graphe conversationnel (create_agent) —
    hérite checkpointer/store du parent. agent_retry_policy : retry
    borné UNIQUEMENT sur erreurs transitoires (None = sans retry).
    """
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
    if agent_retry_policy is not None:
        graph.add_node(
            "agent", subgraph_agent, retry_policy=agent_retry_policy
        )
    else:
        graph.add_node("agent", subgraph_agent)
    graph.add_node("response", response_node)


def register_edges(graph) -> None:
    """Chaîne principale : entrée, retrieval/fallback, sortie."""
    graph.add_edge(START, "intake")
    graph.add_edge("intake", "router")

    graph.add_conditional_edges(
        "router",
        route_after_router,
        {"retrieval": "retrieval", "fallback": "fallback"},
    )
    graph.add_edge("retrieval", "fallback")
    graph.add_edge("fallback", "workflow_router")

    graph.add_edge("context", "learning")
    graph.add_edge("learning", "agent")
    graph.add_edge("agent", "response")
    graph.add_edge("response", END)


def register_workflow_branches(graph) -> None:
    """Branches WORKFLOW_ROUTER + retour des subgraphs vers CONTEXT.

    Point d'insertion des futurs workflows (§88) : ajouter l'entrée
    dans routing.WORKFLOW_BRANCHES + le node dans register_nodes().
    Chaque branche produit son contrat §8 (workflow_result) puis
    rejoint la chaîne principale (CONTEXT → LEARNING → AGENT →
    RESPONSE) — le sous-graphe agentique rédige la réponse.
    """
    graph.add_conditional_edges(
        "workflow_router",
        route_after_workflow_router,
        dict(WORKFLOW_BRANCHES),
    )

    subgraph_returns = (
        ("activity", route_after_activity),
        ("problem", route_after_problem),
        ("research", route_after_research_node),
        ("coding", route_after_coding),
        ("video", route_after_video),
        ("document", route_after_document),
    )
    for node_name, route_fn in subgraph_returns:
        graph.add_conditional_edges(
            node_name,
            route_fn,
            dict(SUBGRAPH_RETURN),
        )


__all__ = [
    "register_nodes",
    "register_edges",
    "register_workflow_branches",
]
