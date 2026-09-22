# SHIM de compatibilité (refactor — phase migration).
#
# CustomAgentState a déménagé vers app/graph/main/state.py.
# SUPPRESSION prévue phase cleanup (§30 mission) après vérification.
from app.graph.main.state import CustomAgentState

__all__ = ["CustomAgentState"]
