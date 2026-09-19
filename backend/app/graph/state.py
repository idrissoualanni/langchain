# Graph State (Phase 1) — MainState typé du Main Graph (§7).
#
# MainState étend le state historique CustomAgentState (MessagesState)
# sans re-créer un système parallèle : il est la forme TYPÉE du
# Main Graph (§83 cible graph/state.py) et reste compatible avec le
# checkpointer SqliteSaver et le sous-graphe create_agent (qui partage
# le même schéma de state).
#
# Canaux ajoutés en Phase 1 :
#   workflow        : WorkflowDecision.model_dump() — décision de
#                     routage vers un workflow (main/activity/...)
#                     émise par le node WORKFLOW_ROUTER.
#   workflow_result : SubgraphResult.model_dump() — résultat structuré
#                     produit par UN subgraph (§8) quand un workflow
#                     en exécute un (Phases 2-7). Présent dès Phase 1
#                     pour fixer le contrat, toujours dict vide sinon.
from pydantic import Field

from app.agent.state import CustomAgentState


class MainState(CustomAgentState):
    """State typé du Main Graph (§7) — sur-ensemble de CustomAgentState.

    MessagesState (hérité) + canaux d'orchestration V7 + canaux
    de routage de workflow (Phase 1). Les nodes parent du Main Graph
    (INTAKE → ROUTER → WORKFLOW_ROUTER → CONTEXT → LEARNING → AGENT →
    RESPONSE) lisent/écrivent ces canaux via le checkpointer.
    """

    # --- Phase 1 : routage de workflow (§4/§5/§8) ---
    intake: dict = Field(
        default_factory=dict,
        description="Entrée normalisée du run (INTAKE) : "
        "{query, user_id, thread_id, interaction_count}",
    )
    workflow: dict = Field(
        default_factory=dict,
        description="WorkflowDecision.model_dump() — décision émise "
        "par WORKFLOW_ROUTER",
    )
    workflow_result: dict = Field(
        default_factory=dict,
        description="SubgraphResult.model_dump() — résultat structuré "
        "produit par UN subgraph (§8), vide en Phase 1",
    )