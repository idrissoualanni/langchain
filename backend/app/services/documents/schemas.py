# SHIM de compatibilité (refactor — phase migration).
#
# Les contrats RAG ont déménagé vers app/schemas/document.py.
# SUPPRESSION prévue phase cleanup (§30 mission) après vérification.
from app.schemas.document import (
    ALLOWED_EXTENSIONS,
    DOCUMENT_SEARCH_STATUS,
    DocumentChunk,
    DocumentRecord,
    DocumentSearchResponse,
    DocumentSearchResult,
)

__all__ = [
    "ALLOWED_EXTENSIONS",
    "DOCUMENT_SEARCH_STATUS",
    "DocumentChunk",
    "DocumentRecord",
    "DocumentSearchResponse",
    "DocumentSearchResult",
]
