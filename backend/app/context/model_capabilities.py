# SHIM de compatibilité (refactor — phase migration).
#
# ModelCapabilities a déménagé vers app/schemas/model_capabilities.py.
# SUPPRESSION prévue phase cleanup (§30 mission) après vérification.
from app.schemas.model_capabilities import (
    ModelCapabilities,
    get_model_capabilities,
    list_configured_models,
    supports,
)

__all__ = [
    "ModelCapabilities",
    "get_model_capabilities",
    "list_configured_models",
    "supports",
]
