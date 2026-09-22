"""Repository des documents utilisateur (façade de ``app.services.documents``)."""
from __future__ import annotations

from app.schemas.document import (
    DocumentRecord,
    DocumentSearchResponse,
)
from app.services.documents import chunker as _chunker_service
from app.services.documents import documents as _documents_service
from app.services.documents import retriever as _retriever_service
from app.services.documents import vector_store as _vector_store_service


def get_rag_store() -> _vector_store_service.RagStore:
    """Retourne le singleton du stockage vectoriel des documents."""
    return _vector_store_service.get_rag_store()


def reset_rag_store() -> None:
    """Réinitialise le singleton du stockage (contexte de test)."""
    _vector_store_service.reset_rag_store()


def chunk_text(
    text: str,
    chunk_tokens: int = _chunker_service.DEFAULT_CHUNK_TOKENS,
    overlap_tokens: int = _chunker_service.DEFAULT_OVERLAP_TOKENS,
) -> list[str]:
    """Découpe un texte en morceaux indexables."""
    return _chunker_service.chunk_text(
        text, chunk_tokens=chunk_tokens, overlap_tokens=overlap_tokens
    )


def extract_text(
    filename: str, raw: bytes, content_type: str | None = None
) -> str:
    """Extrait le texte exploitable d'un fichier téléversé."""
    return _documents_service.extract_text(
        filename, raw, content_type=content_type
    )


def infer_content_type(filename: str) -> str:
    """Déduit le type MIME déclaré depuis l'extension du fichier."""
    return _documents_service.infer_content_type(filename)


def add_document(
    user_id: str,
    filename: str,
    content_type: str,
    text: str,
    chunks: list[str],
) -> DocumentRecord:
    """Indexe un document et ses morceaux pour un utilisateur."""
    return get_rag_store().add_document(
        user_id=user_id,
        filename=filename,
        content_type=content_type,
        text=text,
        chunks=chunks,
    )


def get_document(doc_id: str, user_id: str) -> DocumentRecord | None:
    """Retourne un document précis (None s'il n'existe pas)."""
    return get_rag_store().get_document(doc_id, user_id)


def list_documents(user_id: str) -> list[DocumentRecord]:
    """Liste les documents indexés d'un utilisateur."""
    return get_rag_store().list_documents(user_id)


def delete_document(doc_id: str, user_id: str) -> bool:
    """Supprime un document précis (False s'il n'existe pas)."""
    return get_rag_store().delete_document(doc_id, user_id)


def delete_all_documents(user_id: str) -> int:
    """Supprime tous les documents d'un utilisateur (nombre supprimé)."""
    return get_rag_store().delete_all(user_id)


def search_documents(
    user_id: str,
    query: str,
    top_k: int = 5,
    score_threshold: float = _retriever_service.DEFAULT_SCORE_THRESHOLD,
) -> DocumentSearchResponse:
    """Recherche contrôlée dans les documents d'un utilisateur."""
    retriever = _retriever_service.DocumentRetriever(get_rag_store())
    return retriever.search_documents(
        user_id=user_id,
        query=query,
        top_k=top_k,
        score_threshold=score_threshold,
    )


def inject_documents_context(
    user_id: str,
    query: str,
    max_chunks: int = _retriever_service.MAX_CONTEXT_CHUNKS,
) -> str:
    """Construit le bloc de contexte documentaire pour le prompt."""
    retriever = _retriever_service.DocumentRetriever(get_rag_store())
    return retriever.inject_documents_context(
        user_id=user_id, query=query, max_chunks=max_chunks
    )


__all__ = [
    "get_rag_store",
    "reset_rag_store",
    "chunk_text",
    "extract_text",
    "infer_content_type",
    "add_document",
    "get_document",
    "list_documents",
    "delete_document",
    "delete_all_documents",
    "search_documents",
    "inject_documents_context",
]
