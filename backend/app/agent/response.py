# SHIM de compatibilité (refactor — phase migration).
#
# AgentResponse a déménagé vers app/schemas/response.py (contrat
# central backend↔frontend). SUPPRESSION prévue phase cleanup (§30).
from app.schemas.response import (
    AgentResponse,
    AgentResponseStatus,
    AgentResponseType,
)

__all__ = [
    "AgentResponse",
    "AgentResponseStatus",
    "AgentResponseType",
]
