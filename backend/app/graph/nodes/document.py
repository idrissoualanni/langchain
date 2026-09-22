# DOCUMENT node du Main Graph — DocumentSubgraph (§30).
#
# Quand WORKFLOW_ROUTER décide "document", CE node orchestre la gestion
# documentaire (upload/search/list/delete via la couche documents
# existante) et persiste un SubgraphResult générique (§8) dans
# workflow_result.
#
# §8 prévoit explicitement ce cas : "DocumentSubgraph (§30) : sortie =
# SubgraphResult générique tant que son contrat n'est pas affiné." Le
# node couvre donc l'agenda MCP (§40 : Calendar workflow → calendar MCP
# tools — le serveur agenda expose ses tools via le registry).
from __future__ import annotations

from typing import Any

from app.logging.events import log_event


def document_node(state, config=None) -> dict[str, Any]:
    """DOCUMENT — orchestre la demande documentaire / agenda.

    Entrée : la demande vient du canal `intake.query` (ou du dernier
    message humain). Le payload précise l'action documentaire
    (document_id, action) si fourni.

    Sortie : workflow_result (SubgraphResult générique §8). Les tools
    MCP calendar sont résolus par le sous-graphe agentique (scoping §40)
    — CE node ne fait que confirmer le contrat et enregistrer la demande.
    """
    from app.schemas.workflow import SubgraphResult

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

    workflow_result = SubgraphResult(
        workflow="document",
        status="ok",
        message=(
            f"Demande documentaire prise en compte "
            f"({len(query)} caractères) — résolution par le sous-graphe "
            f"agentique (tools documentaires + MCP agenda)."
        ),
    ).model_dump()

    log_event(
        "DOCUMENT_NODE",
        message=f"Document workflow | query_chars={len(query)}",
        user_id=user_id,
        thread_id=thread_id,
        extra={"operation": "document_node"},
    )

    return {"workflow_result": workflow_result}


def route_after_document(state) -> str:
    """Après DOCUMENT : retour TOUJOURS sur la chaîne principale."""
    return "context"


__all__ = ["document_node", "route_after_document"]
