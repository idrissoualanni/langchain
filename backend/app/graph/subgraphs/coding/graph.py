# SHIM de compatibilité (refactor — phase migration).
#
# Le CodingSubgraph a été standardisé : l'état vit dans state.py et la
# logique + l'assemblage dans nodes.py (compile_coding_subgraph).
# Ce fichier ré-exporte l'API historique (create_coding_subgraph, nodes
# individuels) pour les consommateurs existants.
# SUPPRESSION prévue phase cleanup (§30 mission) après repointage.
from app.graph.subgraphs.coding.nodes import (
    CodingResult,
    CodingState,
    analyze_task,
    compile_coding_subgraph,
    evaluate,
    execute_action,
    finalize,
    finalize_with_limit,
    generate_learning_signals,
    get_coding_subgraph,
    run_coding_workflow,
    should_continue,
)

# Alias historique (appelé par app/graph/nodes/coding.py et les tests).
create_coding_subgraph = compile_coding_subgraph

__all__ = [
    "CodingState",
    "CodingResult",
    "create_coding_subgraph",
    "get_coding_subgraph",
    "run_coding_workflow",
    "analyze_task",
    "execute_action",
    "evaluate",
    "should_continue",
    "compile_coding_subgraph",
]