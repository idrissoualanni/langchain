# Coding Subgraph — CodingState typé (§22-§25).
#
# State INTERNE du subgraph : jamais exposé au Main Graph (les
# subgraphs spécialisés ne le font pas, §5). L'entrée (requête, code,
# langage) arrive par les paramètres explicites de run_coding_workflow ;
# la sortie est produite dans CodingResult (adapter par le node CODING
# vers le contrat §8, cf. app/graph/nodes/coding.py).
from typing import Annotated, Any, Optional, TypedDict

from langgraph.graph.message import add_messages


class CodingState(TypedDict, total=False):
    """État interne du CodingSubgraph (§22).

    Champs publics partagés (entrée) :
      request / user_id / thread_id / language / code

    Champs INTERNES (jamais propagés au Main Graph) :
      task_type / files / errors / test_results / observations /
      iteration / max_iterations / success / final_result
    """

    # --- Entrée (partagée) ---
    request: str
    user_id: Optional[str]
    thread_id: Optional[str]
    language: Optional[str]
    code: Optional[str]

    # --- Interne : plan d'exécution ---
    task_type: Optional[str]  # write, edit, debug, explain, test
    files: list[dict[str, Any]]

    # --- Interne : résultats d'exécution ---
    errors: list[dict[str, Any]]
    test_results: list[dict[str, Any]]
    observations: list[dict[str, Any]]

    # --- Interne : pilotage de la boucle bornée ---
    iteration: int
    max_iterations: int
    success: bool
    final_result: Optional[dict[str, Any]]


__all__ = ["CodingState"]