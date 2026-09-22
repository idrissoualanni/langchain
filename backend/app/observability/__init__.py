# SHIM de compatibilité (refactor — phase migration).
#
# L'observabilité a déménagé vers app/infrastructure/observability/.
# SUPPRESSION prévue phase cleanup (§30 mission) après vérification.
from app.infrastructure.observability import (
    add_example_to_dataset,
    create_dataset,
    get_langsmith_client,
    log_agent_observation,
    set_trace_metadata,
    traceable_agent_action,
)

__all__ = [
    "get_langsmith_client",
    "traceable_agent_action",
    "set_trace_metadata",
    "log_agent_observation",
    "create_dataset",
    "add_example_to_dataset",
]
