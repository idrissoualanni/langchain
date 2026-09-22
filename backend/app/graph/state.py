# SHIM de compatibilité (refactor — phase migration).
#
# MainState a déménagé vers app/graph/main/state.py.
# SUPPRESSION prévue phase cleanup (§30 mission) après vérification.
from app.graph.main.state import CustomAgentState, MainState

__all__ = ["CustomAgentState", "MainState"]
