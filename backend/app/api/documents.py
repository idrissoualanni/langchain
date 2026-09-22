# Routes Documents V10 — RAG / user knowledge (mission).
#
# Pattern identique aux routes memory/users :
#   - ownership validé (_require_owner_or_admin) — user A ne voit
#     JAMAIS les documents de B ;
#   - erreurs d'extraction → 422 contrôlé ;
#   - recherche → statut 4-valeurs contrôlé (jamais de 500).
import base64
import binascii
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas import (
    DocumentOut,
    DocumentSearchResponseOut,
    DocumentUploadCreate,
)
from app.auth.resolver import CurrentUser, get_current_user
from app.services.documents.chunker import chunk_text
from app.services.documents.documents import (
    MAX_FILE_BYTES,
    DocumentExtractError,
    extract_text,
    infer_content_type,
)
from app.services.documents.retriever import DocumentRetriever
from app.services.documents.vector_store import (
    RagStoreError,
    get_rag_store,
)

router = APIRouter(prefix="/api/users", tags=["documents"])


def _require_owner_or_admin(user_id: str, current: CurrentUser) -> None:
    """Ownership : le user_id du chemin doit être le sien (ou admin).

    Implémentation alignée sur routes users (anti-énumération).
    """
    from app.db.connections import init_db
    from app.db.users import get_user

    init_db()
    if current.is_admin:
        return
    if user_id != current.user_id:
        target = get_user(user_id)
        if target is None:
            raise HTTPException(
                status_code=404, detail="Utilisateur introuvable"
            )
        raise HTTPException(
            status_code=403,
            detail="Accès refusé : ressource d'un autre utilisateur",
        )


def _store():
    return get_rag_store()


def _raw_content(payload: DocumentUploadCreate) -> bytes:
    """Reconstitue les octets binaires de l'upload.

    Convention (docstring DocumentUploadCreate) :
      - PDF (extension ou MIME application/pdf) : `content` est le
        fichier encodé en base64 → décodé ici ;
      - texte (md/txt/rst/…) : `content` est le texte brut UTF-8.
    """
    ctype = (payload.content_type or infer_content_type(payload.filename)).lower()
    ext = Path(payload.filename).suffix.lower()
    if ext == ".pdf" or "pdf" in ctype:
        try:
            raw = base64.b64decode(payload.content, validate=False)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(422, "Contenu PDF invalide (base64 attendu)") from exc
    else:
        raw = payload.content.encode("utf-8")
    if len(raw) > MAX_FILE_BYTES:
        raise HTTPException(422, "Fichier trop volumineux (max 2 Mo)")
    return raw


# ------------------------------------------------------------------
# CRUD documents
# ------------------------------------------------------------------


@router.post(
    "/{user_id}/documents",
    response_model=DocumentOut,
    status_code=201,
)
def api_upload_document(
    user_id: str,
    payload: DocumentUploadCreate,
    current: CurrentUser = Depends(get_current_user),
) -> DocumentOut:
    """Upload + indexation d'un document (ownership vérifié)."""
    _require_owner_or_admin(user_id, current)

    raw = _raw_content(payload)

    try:
        text = extract_text(
            payload.filename, raw, payload.content_type
        )
    except DocumentExtractError as exc:
        raise HTTPException(422, str(exc))

    if not text or not text.strip():
        raise HTTPException(
            422, "Aucun contenu textuel extractible de ce fichier"
        )

    try:
        chunks = chunk_text(text)
        record = _store().add_document(
            user_id=user_id,
            filename=payload.filename,
            content_type=payload.content_type or "text/plain",
            text=text,
            chunks=chunks,
        )
    except RagStoreError as exc:
        raise HTTPException(422, str(exc))

    return DocumentOut(
        doc_id=record.doc_id,
        filename=record.filename,
        content_type=record.content_type,
        size_bytes=record.size_bytes,
        chunk_count=record.chunk_count,
        created_at=record.created_at,
    )


@router.get(
    "/{user_id}/documents", response_model=list[DocumentOut]
)
def api_list_documents(
    user_id: str,
    current: CurrentUser = Depends(get_current_user),
) -> list[DocumentOut]:
    """Liste les documents du user (ownership vérifié)."""
    _require_owner_or_admin(user_id, current)
    try:
        docs = _store().list_documents(user_id)
    except RagStoreError:
        raise HTTPException(503, "Stockage documents indisponible")
    return [
        DocumentOut(
            doc_id=d.doc_id,
            filename=d.filename,
            content_type=d.content_type,
            size_bytes=d.size_bytes,
            chunk_count=d.chunk_count,
            created_at=d.created_at,
        )
        for d in docs
    ]


@router.get(
    "/{user_id}/documents/search", response_model=DocumentSearchResponseOut
)
def api_search_documents(
    user_id: str,
    q: str = Query(..., min_length=1, max_length=1000),
    top_k: int = Query(default=5, ge=1, le=20),
    current: CurrentUser = Depends(get_current_user),
) -> DocumentSearchResponseOut:
    """Recherche hybride dans les documents (ownership vérifié)."""
    _require_owner_or_admin(user_id, current)
    retriever = DocumentRetriever(_store())
    resp = retriever.search_documents(
        user_id=user_id, query=q, top_k=top_k
    )
    return DocumentSearchResponseOut(
        status=resp.status,
        query=resp.query,
        error=resp.error,
        results=[r.model_dump() for r in resp.results],
    )


@router.delete("/{user_id}/documents/{doc_id}", status_code=200)
def api_delete_document(
    user_id: str,
    doc_id: str,
    current: CurrentUser = Depends(get_current_user),
) -> dict:
    """Supprime UN document (ownership vérifié)."""
    _require_owner_or_admin(user_id, current)
    try:
        deleted = _store().delete_document(doc_id, user_id)
    except RagStoreError:
        raise HTTPException(503, "Stockage documents indisponible")
    if not deleted:
        raise HTTPException(404, "Document introuvable")
    return {"deleted": True, "doc_id": doc_id}


__all__ = ["router"]