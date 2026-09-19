# Document Tools V10 — RAG / user knowledge (mission).
#
# L'agent dispose de 4 tools documents :
#   upload_document    : indexe UN fichier texte (md/txt/pdf) — le
#                       contenu complet est fourni en argument ;
#   search_documents   : recherche hybride (sémantique+lexicale) dans
#                       les documents de l'utilisateur ;
#   list_documents     : liste les documents indexés ;
#   delete_document    : supprime UN document indexé.
#
# Chaque tool est FAIL-SAFE (mission §15) : jamais d'exception
# propagée au pipeline — une erreur est retournée en chaîne
# contrôlée (le modèle peut la communiquer et continuer).
from langchain_core.tools import tool

from app.logging.events import log_event
from app.rag.documents import (
    DocumentExtractError,
    extract_text,
)
from app.rag.retriever import DocumentRetriever
from app.rag.vector_store import RagStoreError, get_rag_store


def _retriever() -> DocumentRetriever:
    return DocumentRetriever(get_rag_store())


@tool
def upload_document(
    user_id: str,
    filename: str,
    content: str,
) -> str:
    """Indexe UN document personnel de l'utilisateur dans sa base
    de connaissances (RAG V10).

    Formats supportés : texte brut (md, txt, rst) et PDF — pas de
    base64, fournis le contenu TEXTE directement.

    Args:
        user_id: identifiant persistant de l'utilisateur.
        filename: nom du fichier avec son extension
            (ex: "cours-python.md", "cours.pdf").
        content: le contenu complet du document (texte ou contenu
            PDF extrait).

    À utiliser quand l'utilisateur demande d'enregistrer un
    document de cours, de référence ou de projet personnel. Une
    fois indexé, ce document est recherchable via
    search_documents. Retourne un message de confirmation avec
    le nombre de morceaux (chunks) indexés.
    """
    if not content or not content.strip():
        return "Impossible d'indexer : le contenu du document est vide."
    try:
        text = extract_text(
            filename, content.encode("utf-8"), content_type=None
        )
        if not text or not text.strip():
            return (
                "Impossible d'indexer : aucun contenu textuel "
                "extractible de ce fichier."
            )
    except DocumentExtractError as exc:
        return f"Impossible d'indexer le document : {exc}"

    try:
        from app.rag.chunker import chunk_text

        chunks = chunk_text(text)
        record = get_rag_store().add_document(
            user_id=user_id,
            filename=filename,
            content_type="text/plain",
            text=text,
            chunks=chunks,
        )
    except RagStoreError as exc:
        log_event(
            "DOC_UPLOAD_ERROR",
            level="ERROR",
            message=f"upload_document échec: {exc}",
            tool_name="upload_document",
        )
        return f"Erreur pendant l'indexation : {exc}"

    log_event(
        "DOC_UPLOAD",
        message=(
            f"upload_document filename={filename} "
            f"chunks={record.chunk_count}"
        ),
        tool_name="upload_document",
    )
    return (
        f"Document indexé avec succès dans tes connaissances "
        f"personnelles ({record.chunk_count} morceaux).\n"
        f"Fichier : {record.filename}\n"
        f"Tu peux maintenant me poser des questions dessus : "
        f"je le rechercherai automatiquement."
    )


@tool
def search_documents(
    user_id: str,
    query: str,
    top_k: int = 5,
) -> str:
    """Recherche dans les documents personnels de l'utilisateur
    (RAG V10 — recherche hybride sémantique + lexicale).

    Args:
        user_id: identifiant persistant de l'utilisateur.
        query: la question ou le sujet en langage naturel
            (ex: "comment fonctionne la boucle for ?").
        top_k: nombre maximal d'extraits à retourner (1-10).

    À utiliser quand l'utilisateur pose une question susceptible
    d'être couverte par un document qu'il a indexé (cours,
    référence, notes). Retourne les extraits les plus pertinents
    avec leur provenance complète (doc_id, chunk_id, fichier) et
    leur contenu — exploitable pour alimenter un exercice ou une
    évaluation fondés sur le document.
    """
    resp = _retriever().search_documents(
        user_id=user_id,
        query=query,
        top_k=max(1, min(int(top_k), 10)),
    )

    log_event(
        "DOC_SEARCH",
        message=(
            f"search_documents status={resp.status} "
            f"results={len(resp.results)}"
        ),
        tool_name="search_documents",
    )

    if resp.status == "error":
        return (
            "Erreur technique pendant la recherche dans tes "
            "documents. Réponds avec tes connaissances générales."
        )
    if resp.status == "unavailable":
        return (
            "Aucun document personnel indexé pour cette recherche. "
            "Réponds avec tes connaissances générales."
        )
    if resp.status == "insufficient" or not resp.results:
        return (
            "Aucun extrait de tes documents suffisamment pertinent "
            "pour cette question. Réponds avec tes connaissances "
            "générales."
        )

    lines = []
    for i, r in enumerate(resp.results, 1):
        name = r.filename or r.doc_id
        lines.append(
            f"[{i}] {name}\n"
            f"    doc_id: {r.doc_id} | chunk_id: {r.chunk_id}\n"
            f"    pertinence: {r.relevance:.2f}\n"
            f"    contenu: {r.content}"
        )
    return "\n\n".join(lines)


@tool
def list_documents(user_id: str) -> str:
    """Liste les documents personnels indexés de l'utilisateur
    (RAG V10).

    Args:
        user_id: identifiant persistant de l'utilisateur.

    À utiliser quand l'utilisateur demande « quels documents
    as-tu enregistrés ? ». Retourne la liste des fichiers avec
    leur taille et nombre de morceaux.
    """
    try:
        docs = get_rag_store().list_documents(user_id)
    except RagStoreError:
        return "Erreur technique pendant le listing des documents."
    if not docs:
        return (
            "Aucun document personnel indexé pour l'instant. "
            "Je peux en indexer un pour toi (texte, markdown, PDF)."
        )
    lines = [
        f"Documents personnels indexés ({len(docs)}) :",
    ]
    for d in docs:
        size_kb = d.size_bytes / 1024
        lines.append(
            f"  - {d.filename} (doc_id: {d.doc_id}, "
            f"{size_kb:.1f} Ko, {d.chunk_count} morceaux)"
        )
    return "\n".join(lines)


@tool
def delete_document(user_id: str, doc_id: str) -> str:
    """Supprime UN document personnel indexé de l'utilisateur
    (RAG V10).

    Args:
        user_id: identifiant persistant de l'utilisateur.
        doc_id: identifiant du document (visible dans la réponse
            de list_documents côté interface, ou à demander via
            la vue documents).

    À utiliser quand l'utilisateur demande de retirer un document
    de sa base de connaissances.
    """
    try:
        deleted = get_rag_store().delete_document(doc_id, user_id)
    except RagStoreError:
        return "Erreur technique pendant la suppression du document."
    if not deleted:
        log_event(
            "DOC_DELETE_NOT_FOUND",
            level="WARNING",
            message=(
                f"delete_document doc_id={doc_id} "
                f"user_id={user_id} — introuvable"
            ),
            tool_name="delete_document",
        )
        return (
            "Aucun document correspondant à cet identifiant n'a "
            "été trouvé (il a peut-être déjà été supprimé)."
        )
    log_event(
        "DOC_DELETE",
        message=f"delete_document doc_id={doc_id}",
        tool_name="delete_document",
    )
    return "Document supprimé de ta base de connaissances."


document_tools = [
    upload_document,
    search_documents,
    list_documents,
    delete_document,
]

__all__ = ["document_tools"]