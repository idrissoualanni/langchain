# SHIM de compatibilité (refactor — phase migration).
from app.infrastructure.observability.langsmith_client import (
    LangSmithClient,
    add_example_to_dataset,
    create_dataset,
    get_langsmith_client,
    log_agent_observation,
    set_trace_metadata,
    traceable_agent_action,
)

__all__ = [
    "LangSmithClient",
    "add_example_to_dataset",
    "create_dataset",
    "get_langsmith_client",
    "log_agent_observation",
    "set_trace_metadata",
    "traceable_agent_action",
]
