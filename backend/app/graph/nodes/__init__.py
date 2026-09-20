# Nodes du Main Graph (Phase 1).
#
# Les nodes métier existants (ROUTER/RETRIEVAL/FALLBACK/CONTEXT/
# LEARNING/AGENT/RESPONSE) restent dans app.agent.orchestration (§48
# — source de vérité unique) ; app.agent.graph les cablait déjà.
# Phase 1 ajoute DEUX nodes d'orchestration propres au Main Graph :
#
#   INTAKE          (graph/nodes/intake.py) — normalisation d'entrée
#   WORKFLOW_ROUTER (graph/nodes/workflow_router.py) — routage
#                   de workflow (§4/§31 : quel workflow exécuter)
#
# Phase 2 ajoute le node d'ACTIVITÉ (continuation §16/§17) :
#
#   ACTIVITY        (graph/nodes/activity.py) — confirme la
#                   continuation d'une activité en cours et produit
#                   le contrat ActivityResult (§8) avant de rejoindre
#                   la chaîne principale.
#
# Phase 3 ajoute le node PROBLEM (ProblemSubgraph §21) :
#
#   PROBLEM         (graph/nodes/problem.py) — invoque le sous-graphe
#                   problem (résolution déterministe parse→plan→guide
#                   ↺evaluate→validate→artifact) et produit le contrat
#                   ProblemResult (§8) avant de rejoindre la chaîne.
#
# Node = étape d'un workflow ; le plus MINGRE possible (§3/§89).
from app.graph.nodes.activity import (
    activity_node,
    route_after_activity,
)
from app.graph.nodes.intake import intake_node
from app.graph.nodes.problem import (
    problem_node,
    route_after_problem,
)
from app.graph.nodes.workflow_router import (
    route_after_workflow_router,
    WorkflowDecision,
    workflow_router_node,
)

__all__ = [
    "intake_node",
    "workflow_router_node",
    "route_after_workflow_router",
    "WorkflowDecision",
    "activity_node",
    "route_after_activity",
    "problem_node",
    "route_after_problem",
]