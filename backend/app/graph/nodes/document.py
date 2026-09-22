# DOCUMENT node du Main Graph — DocumentSubgraph (§30).
#
# Quand WORKFLOW_ROUTER décide "document", CE node orchestre la gestion
# documentaire via le sous-graphe déterministe DocumentSubgraph (§30) :
#   START → validate_action → dispatch (upload|search|list|delete)
#   → finalize → END
# qui réutilise la couche RAG réelle (services/documents). La sortie
# (DocumentResult §8) est persistée dans workflow_result pour la chaîne
# suivante (CONTEXT → agent).
#
# §8 prévoit ce contrat : "DocumentSubgraph (§30) : sortie =
# DocumentResult affiné (doc_id, filename, action, chunk_count)".
from __future__ import annotations

from typing import Any

from app.logging.events import log_event

_document_subgraph = None


def _document_subgraph_obj():
    """Lazy-init du DocumentSubgraph compilé (cache module)."""
    global _document_subgraph
    if _document_subgraph is None:
        from app.graph.subgraphs.document.nodes import compile_document_subgraph

        _document_subgraph = compile_document_subgraph()
    return _document_subgraph


async def document_node(state, config=None) -> dict[str, Any]:
    """DOCUMENT — exécute le DocumentSubgraph (§30) pour la requête.

    Entrée : la demande vient du canal `intake.query` (ou du dernier
    message humain). Le payload précise l'action documentaire
    (action / filename / content / doc_id / search_query).

    Sortie : workflow_result (DocumentResult §8). Le subgraph est
    déterministe (aucun LLM) et fail-safe (§15) : une action invalide
    ou une erreur RAG est rendue en DocumentResult(status=error), le
    Main Graph ne reçoit jamais d'exception.
    """
    from app.graph.subgraphs.document.nodes import run_document_workflow
    from app.schemas.workflow import DocumentResult

    intake = (state or {}).get("intake") or {}
    query = intake.get("query") if isinstance(intake, dict) else ""
    if not query and isinstance(state, dict):
        query = state.get("query") or ""

    user_id = (state or {}).get("user_id") or ""
    thread_id = ""
    if config:
        thread_id = (
            config.get("configurable") or {}
        ).get("thread_id") or ""

    payload = (state or {}).get("payload") or {} if isinstance(state, dict) else {}

    log_event(
        "DOCUMENT_NODE_START",
        message=f"Document subgraph start | query_chars={len(query)}",
        user_id=user_id,
        thread_id=thread_id,
        extra={"operation": "document_node", "action": payload.get("action")},
    )

    try:
        result = await run_document_workflow(
            user_id=user_id,
            thread_id=thread_id,
            query=query,
            payload=payload,
        )
    except Exception as exc:  # noqa: BLE001 — isolation du run
        log_event(
            "DOCUMENT_NODE_ERROR",
            level="ERROR",
            message=f"Document subgraph failed: {exc}",
            user_id=user_id,
            thread_id=thread_id,
            extra={"operation": "document_node"},
        )
        return {
            "workflow_result": DocumentResult(
                workflow="document",
                status="error",
                message=f"Gestion documentaire en échec : {exc}",
            ).model_dump()
        }

    workflow_result = result.model_dump()

    log_event(
        "DOCUMENT_NODE",
        message=(
            f"Document subgraph run | status={workflow_result.get('status')} "
            f"| action={workflow_result.get('action')} "
            f"| chunks={workflow_result.get('chunk_count')}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        extra={
            "operation": "document_node",
            "status": workflow_result.get("status"),
            "action": workflow_result.get("action"),
            "chunk_count": workflow_result.get("chunk_count"),
        },
    )

    return {"workflow_result": workflow_result}


def route_after_document(state) -> str:
    """Après DOCUMENT : retour TOUJOURS sur la chaîne principale."""
    return "context"


__all__ = ["document_node", "route_after_document"]
