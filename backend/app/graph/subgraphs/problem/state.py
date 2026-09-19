# Problem Subgraph — ProblemState typé (§7/§21).
#
# State INTERNE du subgraph : jamais exposé au Main Graph (les
# subgraphs spécialisés ne le font pas, §5). L'entrée (énoncé +
# soumissions) arrive par des canaux explicites ; la sortie (verdict,
# artefact, score) est rendue dans ProblemResult (§8) via le canal
# workflow_result partagé. Les nodes internes lisent/écrivent les
# canaux ci-dessous.
from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class ProblemState(TypedDict, total=False):
    """État interne du ProblemSubgraph (§21).

    Champs publics partagés avec le Main Graph (entrée/sortie) :
      user_id / thread_id / query      : entrée run
      workflow_result                  : sortie (ProblemResult §8)
      messages                         : messages (history, si fournie)

    Champs INTERNES (jamais propagés au Main Graph) :
      statement / parsed / plan / current_index / attempts /
      step_scores / step_feedback / last_error / rigor /
      next_action                        — détail de la résolution.
    """

    # --- Entrée (partagée) ---
    user_id: str
    thread_id: str
    query: str

    # --- Sortie (partagée) : ProblemResult.model_dump() (§8) ---
    workflow_result: dict

    # --- History (partagée, optionnelle) ---
    messages: Annotated[list, add_messages]

    # --- Interne : parsing (§21) ---
    statement: str
    parsed: dict

    # --- Interne : plan interne + guide ---
    plan: list[dict]
    current_index: int
    attempts: int
    max_attempts: int

    # --- Interne : soumission courante de l'étudiant ---
    submission: str
    guide_message: str

    # --- Interne : référence déterministe optionnelle (évaluation §20) ---
    reference: str

    # --- Interne : verdict global de la résolution ---
    verdict: str

    # --- Interne : évaluation par étape + rigueur ---
    step_scores: list[dict]
    step_feedback: list[dict]
    last_error: dict
    rigor: dict

    # --- Interne : pilotage de la boucle ---
    next_action: str


__all__ = ["ProblemState"]