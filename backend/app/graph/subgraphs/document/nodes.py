# DOCUMENT Subgraph — nodes + assemblage (§30).
#
# Pipeline DÉTERMINISTE (aucun LLM) :
#   START → validate_action → dispatch (upload|search|list|delete)
#          → finalize → END.
# Sortie : DocumentResult (§8, app/schemas/workflow.py). Fail-safe §15 :
# une erreur RAG est capturée et rendue en DocumentResult(status=error),
# jamais propagée au Main Graph.
from __future__ import annotations

from typing import Any

from langgraph.graph import START, END, StateGraph

from app.graph.subgraphs.document.state import DocumentState
from app.schemas.workflow import DocumentResult
from app.logging.events import log_event


# Actions supportées par le subgraph.
ACTIONS: tuple[str, ...] = ("upload", "search", "list", "delete")


def validate_action(state: DocumentState) -> dict[str, Any]:
    """Normalise l'action demandée depuis `payload`.

    Règle : une action EXPLICITE dans payload fait foi — si elle est
    invalide → échec fail-safe immédiat (§15). Sans action explicite,
    déduction heuristique (upload si filename+content, search si query,
    sinon list). Positionne ensuite les paramètres de l'opération dans
    l'état interne.
    """
    payload = state.get("payload") or {}
    query = state.get("query") or ""

    explicit = str(payload.get("action") or "").strip().lower()
    if explicit and explicit not in ACTIONS:
        return {
            **state,
            "action": explicit,
            "error": (
                f"Action documentaire inconnue : {explicit!r} "
                f"(attendue : {'/'.join(ACTIONS)})."
            ),
            "filename": "",
            "content": "",
            "doc_id": "",
            "search_query": "",
            "top_k": 0,
        }

    if explicit:
        action = explicit
    elif payload.get("filename") and payload.get("content"):
        action = "upload"
    elif payload.get("doc_id") and payload.get("delete"):
        action = "delete"
    elif query:
        action = "search"
    else:
        action = "list"

    filename = str(payload.get("filename") or "")
    content = str(payload.get("content") or "")
    doc_id = str(payload.get("doc_id") or "")
    search_query = str(payload.get("search_query") or query or "")
    top_k = int(payload.get("top_k") or 5)

    return {
        **state,
        "action": action,
        "filename": filename,
        "content": content,
        "doc_id": doc_id,
        "search_query": search_query,
        "top_k": top_k,
        "payload": payload,
        "error": "",
    }


def dispatch(state: DocumentState) -> dict[str, Any]:
    """Exécute l'action RAG (upload/search/list/delete) — fail-safe.

    Chaque branche appelle la couche services/documents. Une exception
    est capturée et retournée dans `error` (jamais propagée, §15).
    """
    user_id = state.get("user_id") or ""
    action = state.get("action") or "list"

    # Erreur posée en amont (action invalide) → court-circuit (§15).
    if state.get("error"):
        return {**state}

    try:
        if action == "upload":
            from app.services.documents.chunker import chunk_text
            from app.services.documents.documents import (
                DocumentExtractError,
                extract_text,
            )
            from app.services.documents.vector_store import (
                RagStoreError,
                get_rag_store,
            )

            filename = state.get("filename") or "document.txt"
            content = state.get("content") or ""
            if not content.strip():
                return {**state, "error": "Contenu du document vide."}
            try:
                text = extract_text(filename, content.encode("utf-8"), content_type=None)
            except DocumentExtractError as exc:
                return {**state, "error": f"Extraction impossible : {exc}"}
            if not text.strip():
                return {**state, "error": "Aucun contenu textuel extractible."}
            chunks = chunk_text(text)
            record = get_rag_store().add_document(
                user_id=user_id,
                filename=filename,
                content_type="text/plain",
                text=text,
                chunks=chunks,
            )
            return {
                **state,
                "doc_id": record.doc_id,
                "filename": record.filename,
                "chunk_count": record.chunk_count,
                "data": record,
                "error": "",
            }

        if action == "search":
            from app.services.documents.vector_store import get_rag_store

            query = state.get("search_query") or ""
            top_k = state.get("top_k") or 5
            resp = get_rag_store().search(user_id=user_id, query=query, top_k=top_k)
            if resp.status in ("found", "insufficient"):
                return {
                    **state,
                    "chunk_count": len(resp.results),
                    "data": resp,
                    "error": "",
                }
            return {
                **state,
                "chunk_count": 0,
                "data": resp,
                "error": (
                    resp.error
                    or f"Recherche indisponible ({resp.status}) : "
                    "aucun document indexé pour cet utilisateur."
                ),
            }

        if action == "delete":
            from app.services.documents.vector_store import get_rag_store

            doc_id = state.get("doc_id") or ""
            ok = get_rag_store().delete_document(user_id=user_id, doc_id=doc_id)
            if not ok:
                return {**state, "error": "Document introuvable ou déjà supprimé."}
            return {**state, "chunk_count": 0, "data": {"deleted": doc_id}, "error": ""}

        # list (défaut)
        from app.services.documents.vector_store import get_rag_store

        docs = get_rag_store().list_documents(user_id=user_id)
        total_chunks = sum(getattr(d, "chunk_count", 0) for d in docs)
        return {
            **state,
            "chunk_count": total_chunks,
            "data": docs,
            "error": "",
        }

    except Exception as exc:  # noqa: BLE001 — isolation §15
        log_event(
            "DOC_SUBGRAPH_ERROR",
            level="ERROR",
            message=f"DocumentSubgraph dispatch échec : {exc}",
            extra={"operation": "document_subgraph", "action": action},
        )
        return {**state, "error": str(exc)}


def finalize(state: DocumentState) -> dict[str, Any]:
    """Traduit l'état interne vers le contrat DocumentResult (§8)."""
    error = state.get("error") or ""
    action = state.get("action") or "list"
    chunk_count = int(state.get("chunk_count") or 0)
    filename = state.get("filename") or ""
    doc_id = state.get("doc_id") or ""

    if error:
        status = "error"
        message = f"Action documentaire {action} en échec : {error}"
    else:
        status = "ok"
        message = f"Action documentaire {action} exécutée ({chunk_count} chunks)."

    result = DocumentResult(
        workflow="document",
        status=status,
        message=message,
        doc_id=doc_id,
        filename=filename,
        action=action,
        chunk_count=chunk_count,
    )

    log_event(
        "DOC_SUBGRAPH_RESULT",
        message=f"Document subgraph | action={action} status={status} chunks={chunk_count}",
        extra={"operation": "document_subgraph", "action": action, "status": status},
    )

    return {**state, "workflow_result": result.model_dump()}


# ============================================================================
# GRAPH CONSTRUCTION
# ============================================================================

def compile_document_subgraph():
    """Assemble le DocumentSubgraph compilé (standard §5)."""
    workflow = StateGraph(DocumentState)

    workflow.add_node("validate_action", validate_action)
    workflow.add_node("dispatch", dispatch)
    workflow.add_node("finalize", finalize)

    workflow.add_edge(START, "validate_action")
    workflow.add_edge("validate_action", "dispatch")
    workflow.add_edge("dispatch", "finalize")
    workflow.add_edge("finalize", END)

    return workflow.compile()


_document_subgraph = None


def get_document_subgraph():
    """Instance compilée du DocumentSubgraph (cache module)."""
    global _document_subgraph
    if _document_subgraph is None:
        _document_subgraph = compile_document_subgraph()
    return _document_subgraph


async def run_document_workflow(
    user_id: str,
    thread_id: str,
    query: str = "",
    payload: dict[str, Any] | None = None,
) -> DocumentResult:
    """Exécute le workflow documentaire (contrat interne DocumentResult)."""
    initial_state: DocumentState = {
        "user_id": user_id,
        "thread_id": thread_id,
        "query": query,
        "payload": payload or {},
        "action": "",
        "filename": "",
        "content": "",
        "doc_id": "",
        "search_query": "",
        "top_k": 5,
        "chunk_count": 0,
        "data": None,
        "error": "",
    }

    subgraph = get_document_subgraph()
    final_state = await subgraph.ainvoke(initial_state)

    workflow_result = final_state.get("workflow_result") or {}
    if isinstance(workflow_result, dict):
        return DocumentResult(**workflow_result)
    return workflow_result


__all__ = [
    "DocumentState",
    "DocumentResult",
    "ACTIONS",
    "validate_action",
    "dispatch",
    "finalize",
    "compile_document_subgraph",
    "get_document_subgraph",
    "run_document_workflow",
]