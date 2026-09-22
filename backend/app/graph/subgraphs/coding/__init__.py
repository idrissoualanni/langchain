# Package CodingSubgraph (§22-§25).
#
# Standard §5 : compile_<name>_subgraph() assemble le graphe ; l'état
# (state.py) et les nodes (nodes.py) sont séparés. La sortie est un
# CodingResult INTERNE, adapté vers le contrat §8 par le node CODING.
"""Package CodingSubgraph."""

from app.graph.subgraphs.coding.nodes import (
    CodingResult,
    CodingState,
    compile_coding_subgraph,
    get_coding_subgraph,
    run_coding_workflow,
)

create_coding_subgraph = compile_coding_subgraph

__all__ = [
    "CodingState",
    "CodingResult",
    "compile_coding_subgraph",
    "get_coding_subgraph",
    "run_coding_workflow",
    "create_coding_subgraph",
]