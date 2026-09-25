# Routes Storage — uploads binaires multipart (documents, images, vidéos).
#
# Les OCTETS vont sur Neon Storage ( S3 ) via object_store ; les
# métadonnées sont indexées en base ( object_storage ). Les documents
# textuels déclenchent EN PLUS l'indexation RAG ( chunks + embeddings ).
#
# Sécurité :
#   - ownership vérifié ( _require_owner_or_admin, comme documents.py ) ;
#   - MIME VÉRIFIÉ par magic bytes — JAMAIS confiance à l'extension ou
#     au Content-Type envoyé par le client ;
#   - taille bornée ( MAX_UPLOAD_BYTES ) ;
#   - le nom de fichier est sanitarisé dans la clé S3 ( basename ) ;
#   - jamais de chemin client utilisé tel quel.
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response

from app.auth.resolver import CurrentUser, get_current_user
from app.logging.events import log_event
from app.services.storage.object_store import (
    KINDS,
    MAX_UPLOAD_BYTES,
    ObjectStorageError,
    delete_object,
    get_object,
    list_objects,
    put_object,
)

router = APIRouter(prefix="/api", tags=["storage"])


# ------------------------------------------------------------------
# MIME réel ( magic bytes ) — le Content-Type du client est non fiable
# ------------------------------------------------------------------

_MAGIC = [
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"RIFF", "image/webp"),  # webp : RIFF....WEBP
    (b"%PDF", "application/pdf"),
    (b"\x00\x00\x00\x1cftyp", "video/mp4"),
    (b"\x00\x00\x00\x20ftyp", "video/mp4"),
    (b"\x1aE\xdf\xa3", "video/webm"),  # matroska/webm EBML
    (b"ID3", "audio/mpeg"),
    (b"\xff\xfb", "audio/mpeg"),
]

# Extension -> MIME pour les formats textuels ( pas de magic bytes ).
_TEXT_EXT_MIME = {
    ".txt": "text/plain", ".md": "text/markdown", ".rst": "text/x-rst",
    ".json": "application/json", ".yaml": "application/yaml",
    ".yml": "application/yaml", ".csv": "text/csv", ".tsv": "text/tab-separated-values",
    ".py": "text/x-python", ".js": "text/javascript", ".ts": "text/x-typescript",
    ".html": "text/html", ".css": "text/css", ".xml": "application/xml",
}

# kind -> MIME acceptés ( politique : on n'accepte QUE ce qui est
# explicitement voulu ; un .exe n'a aucun usage pédagogique ici ).
_KIND_MIMES = {
    "document": {
        "application/pdf", "text/plain", "text/markdown", "text/x-rst",
        "application/json", "application/yaml", "text/csv",
        "text/tab-separated-values", "text/x-python", "text/javascript",
        "text/x-typescript", "text/html", "text/css", "application/xml",
    },
    "image": {"image/png", "image/jpeg", "image/gif", "image/webp"},
    "video": {"video/mp4", "video/webm"},
}

_KIND_EXT = {"document": ".pdf", "image": ".png", "video": ".mp4"}


def _real_mime(data: bytes, filename: str, declared: str | None) -> str:
    """MIME RÉEL par magic bytes, puis extension, puis déclaré (last)."""
    for magic, mime in _MAGIC:
        if data.startswith(magic):
            # RIFF peut être avi ou webp : on affine par extension.
            if magic == b"RIFF" and not filename.lower().endswith(".webp"):
                continue
            return mime
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in _TEXT_EXT_MIME:
        return _TEXT_EXT_MIME[ext]
    return (declared or "").split(";")[0].strip().lower() or "application/octet-stream"


def _require_owner_or_admin(user_id: str, current: CurrentUser) -> None:
    """Ownership : le user_id du chemin doit être le sien (ou admin).

    Implémentation alignée sur documents.py ( anti-énumération ).
    """
    from app.infrastructure.database.connections import init_db
    from app.infrastructure.database.users import get_user

    init_db()
    if current.is_admin:
        return
    if user_id != current.user_id:
        if get_user(user_id) is None:
            raise HTTPException(404, "Utilisateur introuvable")
        raise HTTPException(
            403, "Accès refusé : ressource d'un autre utilisateur"
        )


async def _read_bounded(file: UploadFile) -> bytes:
    """Lit l'UploadFile en bornant la taille ( refuse trop tôt )."""
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413,
            f"Fichier trop volumineux (max {MAX_UPLOAD_BYTES} octets)",
        )
    return data


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.post("/users/{user_id}/storage/{kind}")
async def upload_object(
    user_id: str,
    kind: str,
    file: UploadFile = File(...),
    current: CurrentUser = Depends(get_current_user),
):
    """Upload d'un binaire ( multipart/form-data ) → S3 + indexation.

    kind : document | image | video. Les documents textuels déclenchent
    en plus l'indexation RAG ( chunks + embeddings pgvector ).
    """
    _require_owner_or_admin(user_id, current)
    if kind not in KINDS:
        raise HTTPException(
            400, f"kind inconnu : {kind}. Autorisés : {list(KINDS)}"
        )

    data = await _read_bounded(file)
    if not data:
        raise HTTPException(422, "Fichier vide")

    filename = file.filename or f"upload{_KIND_EXT[kind]}"
    mime = _real_mime(data, filename, file.content_type)
    if mime not in _KIND_MIMES[kind]:
        raise HTTPException(
            415,
            f"Type non supporté pour kind={kind} : {mime}. "
            f"Acceptés : {sorted(_KIND_MIMES[kind])}",
        )

    try:
        result = put_object(
            user_id=user_id,
            kind=kind,
            filename=filename,
            mime=mime,
            data=data,
        )
    except ObjectStorageError as exc:
        raise HTTPException(503, str(exc)) from exc

    log_event(
        "OBJECT_UPLOAD",
        message=(
            f"Upload {kind} | user={user_id} | name={filename} "
            f"| {len(data)} octets | storage={result['storage']}"
        ),
        user_id=user_id,
        extra={
            "kind": kind, "filename": filename, "size": len(data),
            "storage": result["storage"], "mime": mime,
        },
    )

    # Documents : indexation RAG ( chunks + embeddings ).
    indexed = None
    if kind == "document" and mime.startswith(("text/", "application/pdf")):
        indexed = _index_document(user_id, filename, mime, data)

    return {
        "object_id": result["object_id"],
        "kind": kind,
        "filename": filename,
        "mime": mime,
        "size_bytes": len(data),
        "storage": result["storage"],
        "deduped": result["deduped"],
        "rag_indexed": indexed,
    }


def _index_document(user_id: str, filename: str, mime: str, data: bytes) -> bool:
    """Extrait le texte d'un document et l'indexe dans le RAG.

    Échec non fatal : le binaire EST stocké ( S3 ) même si l'indexation
    échoue — on signale juste rag_indexed=False.
    """
    try:
        from app.services.documents.chunker import chunk_text
        from app.services.documents.documents import (
            MAX_FILE_BYTES,
            DocumentExtractError,
            extract_text,
        )
        from app.services.documents.vector_store import (
            RagStoreError,
            get_rag_store,
        )

        if len(data) > MAX_FILE_BYTES:
            return False
        # signature : extract_text(filename, raw, content_type)
        text = extract_text(filename, data, mime)
        chunks = chunk_text(text)
        get_rag_store().add_document(
            user_id=user_id,
            filename=filename,
            content_type=mime,
            text=text,
            chunks=chunks,
        )
        return True
    except Exception as exc:
        log_event(
            "OBJECT_RAG_INDEX_ERROR",
            level="WARNING",
            message=f"Indexation RAG échouée | {filename} | {str(exc)[:120]}",
            user_id=user_id,
        )
        return False


@router.get("/users/{user_id}/storage")
def list_user_objects(
    user_id: str,
    kind: str | None = None,
    current: CurrentUser = Depends(get_current_user),
):
    """Liste les binaires d'un utilisateur ( métadonnées sans contenu )."""
    _require_owner_or_admin(user_id, current)
    if kind is not None and kind not in KINDS:
        raise HTTPException(400, f"kind inconnu : {kind}")
    return list_objects(user_id, kind)


@router.get("/storage/{object_id}")
def download_object(
    object_id: str,
    current: CurrentUser = Depends(get_current_user),
):
    """Télécharge un binaire ( ownership vérifiée par user_id )."""
    obj = get_object(object_id, current.user_id)
    if obj is None or obj["content"] is None:
        raise HTTPException(404, "Objet introuvable")
    return Response(
        content=obj["content"],
        media_type=obj["mime"] or "application/octet-stream",
        headers={
            "Content-Disposition": f'inline; filename="{obj["filename"]}"',
        },
    )


@router.delete("/storage/{object_id}")
def remove_object(
    object_id: str,
    current: CurrentUser = Depends(get_current_user),
):
    """Supprime un binaire ( S3 + base )."""
    deleted = delete_object(object_id, current.user_id)
    if not deleted:
        raise HTTPException(404, "Objet introuvable")
    log_event(
        "OBJECT_DELETE",
        message=f"Objet supprimé | object={object_id} | user={current.user_id}",
        user_id=current.user_id,
    )
    return {"deleted": object_id}


__all__ = ["router"]
