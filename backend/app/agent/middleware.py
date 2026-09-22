# SHIM de compatibilité (refactor — phase migration).
#
# Le middleware a déménagé vers app/services/agent/middleware.py.
# SUPPRESSION prévue phase cleanup (§30 mission) après vérification.
from app.services.agent.middleware import (
    DOCUMENT_TOOL_NAMES,
    LEARNING_TOOL_NAMES,
    MEMORY_TOOL_NAMES,
    build_middleware_stack,
    get_last_context,
    register_activity,
    tutor_dynamic_prompt,
)

__all__ = [
    "MEMORY_TOOL_NAMES",
    "LEARNING_TOOL_NAMES",
    "DOCUMENT_TOOL_NAMES",
    "build_middleware_stack",
    "get_last_context",
    "register_activity",
    "tutor_dynamic_prompt",
]
