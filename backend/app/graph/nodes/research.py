# RESEARCH node du Main Graph — délègue au ResearchSubgraph (§26-§27).
#
# Quand WORKFLOW_ROUTER décide "research" (hint @deep-research /
# @academic-search / @news-search du composer, ou routage interne),
# CE node invoque le sous-graphe research
# (PLAN → RESEARCH ↺ → EXTRACT_CLAIMS → VERIFY → SYNTHESIZE) et
# persiste le ResearchResult (§8) dans workflow_result pour la chaîne
# suivante (CONTEXT → agent).
#
# Le sous-graphe est DÉTERMINISTE et stateless (aucun LLM, aucune
# persistance interne) ; il n'expose que workflow_result. Le node
# rejoint ensuite la chaîne principale (comme PROBLEM, §21).
from __future__ import annotations

from typing import Any

from app.graph.subgraphs.research.nodes import (
    compile_research_subgraph,
    build_initial_state,
)
from app.logging.events import log_event

_compiled_research = None

# Objectives pédagogiques des mentions research du composer. Le
# ResearchSubgraph consomme payload["objective"] pour orienter la
# synthèse (priorité académique / actualité / profondeur).
_RESEARCH_OBJECTIVES: dict[str, str] = {
    "deep-research": "Recherche approfondie multi-sources avec analyse critique",
    "academic-search": "Priorité aux articles scientifiques et publications",
    "news-search": "Sources d'actualité récentes (48h)",
}


def _research_subgraph():
    global _compiled_research
    if _compiled_research is None:
        _compiled_research = compile_research_subgraph()
    return _compiled_research


def research_node(state, config=None) -> dict[str, Any]:
    """RESEARCH — exécute le ResearchSubgraph pour la requête courante.

    Entrée : la question vient du canal `intake.query` (ou du dernier
    message humain). L'objective est dérivé de la mention origine
    (payload `research_mode`) quand le composer l'a fournie.

    Sortie : invoque le sous-graphe compilé et récupère son
    `workflow_result` (ResearchResult §8). Si le sous-graphe ne produit
    rien, résultat partiel (non-régression, jamais de crash).
    """
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

    # Payload : objective pédagogique selon la mention d'origine.
    payload: dict = {}
    research_mode = ""
    if isinstance(state, dict):
        research_mode = str(
            (state.get("payload") or {}).get("research_mode") or ""
        )
    if research_mode and research_mode in _RESEARCH_OBJECTIVES:
        payload["objective"] = _RESEARCH_OBJECTIVES[research_mode]

    sub = _research_subgraph()
    initial = build_initial_state(
        query=query,
        user_id=user_id,
        thread_id=thread_id,
        payload=payload,
    )
    try:
        result = sub.invoke(initial)
    except Exception as exc:  # noqa: BLE001 — isolation du run
        from app.schemas.workflow import ResearchResult

        log_event(
            "RESEARCH_NODE_ERROR",
            level="ERROR",
            message=f"Research subgraph failed: {exc}",
            user_id=user_id,
            thread_id=thread_id,
            extra={"operation": "research_node"},
        )
        return {
            "workflow_result": ResearchResult(
                workflow="research",
                status="error",
                message=f"Recherche en échec : {exc}",
            ).model_dump()
        }

    workflow_result = result.get("workflow_result") or {}
    if not workflow_result:
        from app.schemas.workflow import ResearchResult

        workflow_result = ResearchResult(
            workflow="research",
            status="partial",
            message="Aucun résultat de recherche produit (requête vide ?)",
        ).model_dump()

    log_event(
        "RESEARCH_NODE",
        message=(
            f"Research subgraph run | query_chars={len(query)} "
            f"| status={workflow_result.get('status')} "
            f"| claims={len(workflow_result.get('claims') or [])}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        extra={
            "operation": "research_node",
            "status": workflow_result.get("status"),
            "objective": payload.get("objective", ""),
        },
    )

    return {"workflow_result": workflow_result}


def route_after_research_node(state) -> str:
    """Après RESEARCH : retour TOUJOURS sur la chaîne principale.

    La recherche a produit son ResearchResult ; le sous-graphe agentique
    rédige ensuite la réponse à partir de workflow_result.
    """
    return "context"


__all__ = ["research_node", "route_after_research_node"]
