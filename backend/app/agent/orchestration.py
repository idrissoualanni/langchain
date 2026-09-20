# Orchestration LangGraph V7 — nodes parent du graphe unique
# (mission ORCHESTRATION).
#
# Chaque node APPELLE RÉELLEMENT le service métier correspondant
# (§48 — source de vérité unique) puis PERSISTE son résultat
# (dict sérialisable) dans le state LangGraph. L'aval consomme
# ces canaux sans re-exécuter :
#
#   ROUTER    → route_subject()              → routing_result
#   RETRIEVAL → retrieve_sources()           → knowledge + web
#   FALLBACK  → decide_fallback()            → fallback
#   CONTEXT   → build_context() (sous-résultats pré-calculés)
#                                           → built_context
#   LEARNING  → decide()                     → learning_decision
#   RESPONSE  → normalize_response()         → agent_response
#
# Conditionnel : supported/multi_domain → RETRIEVAL ; sinon
# FALLBACK direct (rien à chercher : ambiguous/unknown/unsupported).
#
# Graphe type (parent) :
#   START → ROUTER →[retrieval|fallback] → FALLBACK → CONTEXT →
#   LEARNING → AGENT (sous-graphe create_agent) → RESPONSE → END
#
# Contrat des nodes : (state, config) → dict de canaux à écrire.
# Le state reçu est un Mapping (CustomAgentState, MessagesState
# dict-grade) — accès par clé, jamais par attribut.
from app.context import retrieve_sources
from app.context.builder import build_context
from app.context.fallback import decide_fallback
from app.context.router import route_subject
from app.context.schemas import (
    BuiltContext,
    FallbackDecision,
    KnowledgeSearchResult,
    RoutingResult,
    SearchResponse,
)
from app.logging.events import log_event
from app.subjects.registry import get_subject

__all__ = [
    "router_node",
    "retrieval_node",
    "fallback_node",
    "context_node",
    "learning_node",
    "response_node",
    "route_after_router",
]


def _thread_id(config) -> str:
    """thread_id depuis la config LangGraph (configurable)."""
    if not config:
        return ""
    return (config.get("configurable") or {}).get("thread_id") or ""


def _user_id(state) -> str:
    """user_id depuis le state (canal persisté)."""
    return state.get("user_id") or ""


def _last_user_query(state) -> str:
    """Dernier message humain du state (sélection contextuelle)."""
    from langchain_core.messages import HumanMessage

    for m in reversed(state.get("messages") or []):
        if isinstance(m, HumanMessage):
            content = m.content
            if isinstance(content, str):
                return content
            return str(content)
    return ""


def _last_ai_message(state) -> str:
    """Contenu du dernier message assistant du state."""
    from langchain_core.messages import AIMessage

    for m in reversed(state.get("messages") or []):
        if isinstance(m, AIMessage):
            content = m.content
            if isinstance(content, str):
                return content
            return str(content)
    return ""


def router_node(state, config=None) -> dict:
    """ROUTER — classification de la demande (§14-§15).

    Appel réel : route_subject(query). Résultat persisté en dict.
    """
    query = _last_user_query(state)
    user_id = _user_id(state)
    thread_id = _thread_id(config)

    routing = route_subject(query)
    log_event(
        "ROUTING_COMPUTED",
        message=(
            f"Routing computed | status={routing.status} | "
            f"subject={routing.subject or '-'}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        extra={
            "operation": "router_node",
            "routing_status": routing.status,
            "subject": routing.subject,
            "topic": routing.topic,
        },
    )
    return {"routing_result": routing.model_dump()}


def retrieval_node(state, config=None) -> dict:
    """RETRIEVAL — recherche knowledge locale + web fallback.

    Appel réel : retrieve_sources() (source de vérité UNIQUE §48,
    partagé avec build_context). Résultats persistés en dicts.
    """
    from app.context.schemas import RoutingResult as _R

    routing = _R.model_validate(
        state.get("routing_result") or {}
    )
    query = _last_user_query(state)
    user_id = _user_id(state)
    thread_id = _thread_id(config)

    cfg = get_subject(routing.subject) if routing.subject else None

    knowledge, web = retrieve_sources(
        user_id=user_id,
        thread_id=thread_id,
        query=query,
        routing=routing,
        cfg=cfg,
    )
    return {
        "knowledge": knowledge.model_dump(),
        "web": web.model_dump(),
    }


def fallback_node(state, config=None) -> dict:
    """FALLBACK — décision structurée proactive (§6 V6.6).

    Consomme routing/knowledge/web et produit UNE action
    (matrice pure, testable sans LLM). Appel réel : decide_fallback.
    """
    routing = RoutingResult.model_validate(
        state.get("routing_result") or {}
    )
    knowledge = KnowledgeSearchResult.model_validate(
        state.get("knowledge") or {}
    )
    web = SearchResponse.model_validate(state.get("web") or {})
    query = _last_user_query(state)
    user_id = _user_id(state)
    thread_id = _thread_id(config)

    fallback = decide_fallback(
        routing_status=routing.status,
        subject=routing.subject,
        topic=routing.topic,
        knowledge_status=knowledge.status,
        web_status=web.status,
        has_web_results=bool(web.results),
        query=query,
        user_id=user_id,
        thread_id=thread_id,
    )
    if routing.status == "ambiguous":
        fallback.candidates = list(routing.candidates)
    return {"fallback": fallback.model_dump()}


def context_node(state, config=None) -> dict:
    """CONTEXT — assemblage final du BuiltContext.

    Appel réel : build_context() (source de vérité UNIQUE).
    Les sous-résultats PRÉ-CALCULÉS par les nodes précédents sont
    passés à build_context — il ne ré-exécute PAS les services
    (§48), il assemble (documents, tools, mémoire, budget...).
    """
    routing = RoutingResult.model_validate(
        state.get("routing_result") or {}
    )
    knowledge = KnowledgeSearchResult.model_validate(
        state.get("knowledge") or {}
    )
    web = SearchResponse.model_validate(state.get("web") or {})
    fallback = FallbackDecision.model_validate(
        state.get("fallback") or {}
    )
    query = _last_user_query(state)
    user_id = _user_id(state)
    thread_id = _thread_id(config)
    learning_activity = state.get("learning_activity") or None

    context = build_context(
        user_id=user_id,
        thread_id=thread_id,
        query=query,
        learning_activity=(
            learning_activity if isinstance(learning_activity, dict) else None
        ),
        routing=routing,
        knowledge=knowledge,
        web=web,
        fallback=fallback,
    )
    return {"built_context": context.model_dump()}


def learning_node(state, config=None) -> dict:
    """LEARNING — décision pédagogique (Learning Engine).

    Appel réel : decide(built_context). La décision est persistée
    en dict et consommée par le dynamic_prompt (add_learning_strategy_block).
    """
    from app.learning.decision import LearningDecision
    from app.learning.engine import decide

    context = BuiltContext.model_validate(
        state.get("built_context") or {}
    )
    user_id = _user_id(state)
    thread_id = _thread_id(config)

    decision = decide(context, user_id=user_id, thread_id=thread_id)
    return {"learning_decision": decision.model_dump()}


def _web_results_from_context(state) -> tuple:
    """Extrait (search_results, search_used) du built_context.

    Source de vérité : le BuiltContext assemblé par le node CONTEXT
    (post-budget — les résultats droppés par le budget ne doivent
    PAS réapparaître, §44).
    """
    try:
        from app.context.schemas import BuiltContext as _B

        context = _B.model_validate(
            state.get("built_context") or {}
        )
    except Exception:
        return None, False
    web = getattr(context, "web", None)
    if web is None:
        return None, False
    results = [r.model_dump() for r in web.results]
    return results, (web.status == "found" and bool(web.results))


def response_node(state, config=None) -> dict:
    """RESPONSE — contrat public final (AgentResponse).

    Appel réel : normalize_response(). L'état complet est déjà
    présent (messages, activité, fallback, search). Le runner
    utilise state.agent_response quand présent ; sinon il garde
    le comportement historique (non-régression).
    """
    from app.agent.normalizer import normalize_response

    message = _last_ai_message(state)
    activity = state.get("learning_activity") or None
    if not isinstance(activity, dict):
        activity = None
    fallback = None
    try:
        fallback = FallbackDecision.model_validate(
            state.get("fallback") or {}
        )
    except Exception:
        fallback = None

    search_results, search_used = _web_results_from_context(state)

    response = normalize_response(
        message=message,
        activity=activity,
        search_results=search_results,
        search_used=search_used,
        fallback=fallback,
    )
    return {"agent_response": response.model_dump()}


def route_after_router(state) -> str:
    """Conditionnel après ROUTER.

    supported/multi_domain → retrieval (il y a une matière à
    chercher) ; ambiguous/unknown/unsupported → fallback direct
    (pas d'ancrage de recherche §36, clarification ou tutor
    général décidés par decide_fallback).
    """
    routing = state.get("routing_result") or {}
    status = routing.get("status") or "unknown"
    return "retrieval" if status in ("supported", "multi_domain") else "fallback"