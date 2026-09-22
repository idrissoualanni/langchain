# SHIM de compatibilité (refactor — phase migration).
#
# L'assemblage + factory ont déménagé vers app/graph/main/graph.py.
# SUPPRESSION prévue phase cleanup (§30 mission) après vérification.
from app.graph.main.graph import (
    all_tools,
    build_graph,
    compile_main_graph,
    get_agent,
)

__all__ = [
    "all_tools",
    "build_graph",
    "compile_main_graph",
    "get_agent",
]
