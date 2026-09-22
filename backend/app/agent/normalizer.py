# SHIM de compatibilité (refactor — phase migration).
#
# normalize_response a déménagé vers app/services/agent/normalizer.py.
# SUPPRESSION prévue phase cleanup (§30 mission) après vérification.
from app.services.agent.normalizer import (
    normalize_response,
    response_from_activity,
    response_from_clarification,
    response_from_error,
    response_from_search,
    response_from_text,
)

__all__ = [
    "normalize_response",
    "response_from_activity",
    "response_from_search",
    "response_from_clarification",
    "response_from_error",
    "response_from_text",
]
