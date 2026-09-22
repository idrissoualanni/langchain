# SHIM de compatibilité (refactor — phase migration).
#
# Le runner a déménagé vers app/services/agent/runner.py (service
# d'invocation du graphe : API → Service → Graph).
# SUPPRESSION prévue phase cleanup (§30 mission) après vérification.
from app.services.agent.runner import (
    _config_for,
    get_thread_history,
    get_thread_state,
    run_agent,
    run_agent_stream,
)

__all__ = [
    "_config_for",
    "get_thread_history",
    "get_thread_state",
    "run_agent",
    "run_agent_stream",
]
