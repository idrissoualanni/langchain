# RAG Schemas V10 — schémas structurés du module documents utilisateur.
#
# Contrats (convention extra=forbid comme le reste du projet V6.8.1) :
#   DocumentRecord    : UN document uploadé (métadonnées, pas les chunks)
#   DocumentChunk     : UN morceau du document (contenu + emb)
#   DocumentSearchResult : résultat de recherche hybride
#   DocumentSearchResponse : réponse complète (statut contrôlé)
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Statuts contrôlés d'une recherche document (§19 style) :
#   found        → ≥1 résultat ≥ seuil
#   insufficient → parcouru, rien de pertinent
#   unavailable  → aucune source (pas de provider / pas de docs)
#   error        → échec technique (contrôlé, jamais propagé)
DOCUMENT_SEARCH_STATUS = (
    "found",
    "insufficient",
    "unavailable",
    "error",
)

# Formats acceptés à l'upload (sender : text/plain pour md/txt).
ALLOWED_EXTENSIONS = ("md", "txt", "pdf", "markdown", "rst")


class DocumentRecord(BaseModel):
    """UN document utilisateur indexé.

    model_config extra=forbid : contrat strict — aucun champ
    parallèle implicite.
    """

    model_config = {"extra": "forbid"}

    doc_id: str = Field(description="Identifiant unique du document")
    user_id: str = Field(description="Propriétaire (isolation stricte)")
    filename: str = Field(description="Nom de fichier original")
    content_type: str = Field(
        default="text/plain",
        description="Type MIME déclaré",
    )
    size_bytes: int = Field(
        default=0,
        ge=0,
        description="Taille du texte indexé (octets)",
    )
    chunk_count: int = Field(
        default=0,
        ge=0,
        description="Nombre de chunks stockés",
    )
    created_at: str = Field(
        default="",
        description="Horodatage ISO 8601 UTC",
    )


class DocumentChunk(BaseModel):
    """UN chunk d'un document (unité de retrieval)."""

    model_config = {"extra": "forbid"}

    chunk_id: str = Field(description="Identifiant du chunk")
    doc_id: str = Field(description="Document parent")
    user_id: str = Field(description="Propriétaire")
    index: int = Field(default=0, ge=0, description="Position dans le doc")
    content: str = Field(
        default="",
        description="Texte du chunk (source du LLM)",
    )
    embedding: list[float] = Field(
        default_factory=list,
        description="Vecteur d'embedding (dim = provider actif)",
    )


class DocumentSearchResult(BaseModel):
    """UN chunk pertinent retrouvé.

    Hérite de la forme SearchResult du contrat retrieval V6.5 :
    source_type = "user_document" (le champ existe déjà dans le
    schéma SearchResult — cohérence, aucune technologie nouvelle).
    """

    model_config = {"extra": "forbid"}

    doc_id: str = ""
    chunk_id: str = ""
    filename: str = ""
    source: str = Field(
        default="user_document",
        description="Origine (cohérent avec SearchResult V6.5)",
    )
    content: str = Field(description="Contenu exploitable du chunk")
    relevance: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Score hybride [0..1]",
    )
    lexical_score: float = Field(default=0.0, ge=0.0, le=1.0)
    semantic_score: float = Field(default=0.0, ge=0.0, le=1.0)
    metadata: dict = Field(
        default_factory=dict,
        description="index, chunk_count, created_at…",
    )


class DocumentSearchResponse(BaseModel):
    """Réponse contrôlée d'une recherche dans les documents user.

    Statut 4-valeurs (found/insufficient/unavailable/error) —
    jamais réduit à « not found » (mission V6.6 §7).
    """

    model_config = {"extra": "forbid"}

    status: Literal[  # noqa: PIE800
        "found",
        "insufficient",
        "unavailable",
        "error",
    ] = Field(default="unavailable")
    query: str = Field(
        default="",
        description="Requête normalisée réellement cherchée",
    )
    results: list[DocumentSearchResult] = Field(
        default_factory=list
    )
    error: str = Field(
        default="",
        description="Cause d'erreur loggée (jamais exposée brute)",
    )


__all__ = [
    "ALLOWED_EXTENSIONS",
    "DOCUMENT_SEARCH_STATUS",
    "DocumentChunk",
    "DocumentRecord",
    "DocumentSearchResponse",
    "DocumentSearchResult",
]