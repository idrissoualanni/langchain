# SHIM de compatibilité (refactor — phase migration).
#
# L'assemblage a déménagé vers app/graph/main/ (graph.py + edges.py
# + routing.py + state.py). SUPPRESSION prévue phase cleanup (§30).
from app.graph.main.graph import compile_main_graph
from app.graph.main.state import MainState

__all__ = ["compile_main_graph", "MainState"]
