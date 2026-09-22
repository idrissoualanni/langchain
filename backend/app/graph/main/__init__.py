# Main Graph — orchestration principale (§4 mission refactor).
#
#   state.py   : CustomAgentState + MainState (états typés)
#   routing.py : table de routage workflow → node
#   edges.py   : register_nodes / register_edges / register_workflow_branches
#   graph.py   : compile_main_graph + factory (get_agent/build_graph)
from app.graph.main.edges import (
    register_edges,
    register_nodes,
    register_workflow_branches,
)
from app.graph.main.graph import (
    all_tools,
    build_graph,
    compile_main_graph,
    get_agent,
)
from app.graph.main.routing import SUBGRAPH_RETURN, WORKFLOW_BRANCHES
from app.graph.main.state import CustomAgentState, MainState

__all__ = [
    "CustomAgentState",
    "MainState",
    "SUBGRAPH_RETURN",
    "WORKFLOW_BRANCHES",
    "all_tools",
    "build_graph",
    "compile_main_graph",
    "get_agent",
    "register_edges",
    "register_nodes",
    "register_workflow_branches",
]
