# Main Graph — assemblage de l'orchestration unique (§26/§63).
#
# Fusion refactor :
#   - compile_main_graph (ex app/graph/main.py) : assemble le StateGraph
#     sur MainState via register_nodes/register_edges/
#     register_workflow_branches — ce module connecte UNIQUEMENT ;
#   - FACTORY d'agent (ex app/agent/graph.py) : model/tools/
#     checkpointer/store/middleware — fournis au graphe parent.
#
# Toute la logique métier vit dans les couches (router/fallback/
# builder/learning/normalizer), appelée RÉELLEMENT par les nodes
# (app/agent/orchestration, §48 — migré vers services/agent/).
#
# Défense d'un checkpointer UNIQUE : le sous-graphe create_agent
# est compilé SANS checkpointer ni store — il HÉRITE ceux du graphe
# parent (POC-3 validé : get_state/get_state_history fonctionnent,
# tables checkpoints/writes créées par le parent). state_schema et
# context_schema sont partagés → request.state du middleware expose
# built_context/learning_decision (POC-2).
import inspect
import sqlite3

from langchain.agents import create_agent
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph
from langgraph.types import RetryPolicy

from app.services.memory.memory import get_store
from app.config import (
    AGENT_RECURSION_LIMIT,
    CHECKPOINTS_DB_PATH,
    MODEL_NAME,
    MODEL_RETRY_ATTEMPTS,
)
from app.services.agent.middleware import build_middleware_stack
from app.services.agent.prompts import SYSTEM_PROMPT
from app.graph.main.edges import (
    register_edges,
    register_nodes,
    register_workflow_branches,
)
from app.graph.main.state import CustomAgentState, MainState

# Tools LLM (source unique app/tools/ — agrégat all_tools).
from app.tools import all_tools
from app.schemas.context import AgentContext
from app.logging.events import log_event
from app.services.models.retry import is_transient_error

_conn: sqlite3.Connection | None = None
_agent = None

# Mission Assistant UI (ModelSelector) : cache d'agents par modele.
# L'instance par defaut (MODEL_NAME de l'env) reste _agent ; les
# autres modeles selectionnes via le ModelSelector obtiennent leur
# propre instance, avec le MEME checkpointer/store (persistance
# inchangee). Cablage uniquement - aucune logique pedagogique (§63).
_agents_by_model: dict = {}


def get_agent(model=None):
    """Singleton agent — initialisé au startup FastAPI (lifespan).

    "model" : modele optionnel (ModelSelector assistant-ui).
    None/"" ou modele par defaut -> instance par defaut (MODEL_NAME).

    Mission §7 — provider client restreint : un choix client n'est
    accepté QUE s'il correspond à un modèle ENREGISTRÉ (id ou nom
    réel du registry) ET enabled. Sinon → repli silencieux tracé
    (événement MODEL_SELECTOR_REJECTED) sur l'instance par défaut.
    """
    global _conn, _agent

    if model:
        model = str(model).strip()
        if model and model != MODEL_NAME:
            from app.services.models.registry import (
                find_model_config,
                get_default_model_id,
            )

            registered = find_model_config(model)
            if registered is None or not registered.enabled:
                log_event(
                    "MODEL_SELECTOR_REJECTED",
                    level="WARNING",
                    message=(
                        f"Modèle '{model}' non enregistré ou désactivé "
                        f"— repli sur l'instance par défaut (admin only)"
                    ),
                    extra={"operation": "get_agent", "model_selector": model},
                )
                model = None
            elif registered.id == get_default_model_id():
                # Sélection explicite du modèle par défaut → PAS de
                # seconde instance (même checkpointer/store).
                model = None
            else:
                key = registered.id
                cached = _agents_by_model.get(key)
                if cached is not None:
                    return cached
                agent = _build_agent(key)
                _agents_by_model[key] = agent
                return agent
        else:
            model = None

    if _agent is not None:
        return _agent
    _agent = _build_agent(None)
    return _agent


def build_graph():
    """Entrypoint langgraph.json — graphe parent compilé.

    Point d'entrée pour le CLI/dev (langgraph dev) : retourne le
    même graphe d'orchestration que get_agent(), avec le
    checkpointer SQLite unique et le store longue durée.
    """
    return _build_agent(None)


def compile_main_graph(subgraph_agent, checkpointer, store):
    """Assemble et compile le Main Graph sur MainState.

    subgraph_agent : sous-graphe agentique (create_agent) — le
    sous-graphe conversationnel (§5) hérite checkpointer/store du
    graphe parent (POC-3).
    checkpointer   : persistance du thread state (SqliteSaver).
    store          : mémoire longue durée cross-thread.

    Limites (mission §3, lues depuis app/config.py — jamais de
    valeur hardcodée ici) :
      - node AGENT : retry policé borné (retry_policy, max_attempts
        configurables, UNIQUEMENT sur erreurs transitoires via
        is_transient_error)
      - timeout : PAS passé au node (timeout= n'est supporté par
        LangGraph que pour les nodes ASYNC ; le node agent est sync).
        Il est ENFORCÉ par le runner (I/O boundary) via wait_for
        (AGENT_TIMEOUT_SECONDS dans invoke_llm_with_retry).
      - recursion_limit : passé au compile quand la version de
        LangGraph le supporte ; il est TOUJOURS appliqué par la
        config d'invocation du runner (point d'application réel).
    """
    agent_retry_policy = RetryPolicy(
        initial_interval=0.5,
        backoff_factor=2.0,
        max_interval=4.0,
        max_attempts=MODEL_RETRY_ATTEMPTS,
        jitter=True,
        retry_on=is_transient_error,
    )

    graph = StateGraph(MainState)
    register_nodes(graph, subgraph_agent, agent_retry_policy)
    register_edges(graph)
    register_workflow_branches(graph)

    compile_kwargs: dict = {"checkpointer": checkpointer, "store": store}
    if "recursion_limit" in inspect.signature(StateGraph.compile).parameters:
        compile_kwargs["recursion_limit"] = AGENT_RECURSION_LIMIT

    return graph.compile(**compile_kwargs)


def _build_subgraph_agent(model_name):
    """Sous-graphe AGENT (create_agent) — SANS checkpointer ni store.

    Le thread state est persisté par le CHECKPOINTER UNIQUE du
    graphe parent (POC-3) : le sous-graphe hérite le checkpointer
    de son contexte d'exécution. Le store long terme est un
    singleton module (app.services.memory.get_store) — pas besoin de
    le passer ici (POC-3).

    Instanciation via Model Gateway SEULEMENT (§1 mission) : jamais
    de ChatOllama/ChatOpenAI en dur ici. Gate de capabilities (§4) :
    un modèle sans supports_tools → agent SANS tools (fallback
    documenté via l'événement MODEL_NO_TOOLS).
    """
    llm, tools = _resolve_llm_and_tools(model_name)

    return create_agent(
        model=llm,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        state_schema=CustomAgentState,
        context_schema=AgentContext,  # Runtime Context natif (§4)
        middleware=build_middleware_stack(),
    )


def _resolve_llm_and_tools(model_name):
    """Résout (llm, tools) : registry → resolver → gateway (§1/§4).

    - model_name None/"" → modèle défaut par purpose ("default")
    - model_name enregistré → create_llm_from_config (id logique)
    - gate tools : supports_tools=False → [] + événement documenté
    - modèle défaut indisponible → ModelGatewayError contrôlé
    """
    from app.services.models.gateway import (
        ModelGatewayError,
        create_llm_from_config,
        get_llm_for_purpose,
    )
    from app.services.models.registry import find_model_config
    from app.services.models.resolver import resolve_model_for_purpose

    if model_name:
        config = find_model_config(model_name)
        if config is None or not config.enabled:
            log_event(
                "MODEL_NO_TOOLS" if config is not None else "MODEL_NOT_FOUND",
                level="WARNING",
                message=(
                    f"Modèle '{model_name}' non enregistré ou désactivé "
                    f"— repli sur défaut"
                ),
                extra={"operation": "_resolve_llm_and_tools"},
            )
            model_name = None
        else:
            llm = create_llm_from_config(config.id)
            if not config.capabilities.supports_tools:
                log_event(
                    "MODEL_NO_TOOLS",
                    level="WARNING",
                    message=(
                        f"Modèle '{config.id}' sans supports_tools — "
                        f"agent créé SANS tools (fallback documenté, §4)"
                    ),
                    extra={
                        "operation": "_resolve_llm_and_tools",
                        "model_id": config.id,
                    },
                )
                return llm, []
            return llm, all_tools

    # Modèle par défaut via resolver (déterministe, aucun LLM)
    result = resolve_model_for_purpose(purpose="default")
    if result.is_enabled and result.config:
        llm = get_llm_for_purpose("default")
        if result.config.capabilities.supports_tools:
            return llm, all_tools
        log_event(
            "MODEL_NO_TOOLS",
            level="WARNING",
            message=(
                f"Modèle défaut '{result.config.id}' sans supports_tools "
                f"— agent créé SANS tools (fallback documenté, §4)"
            ),
            extra={"operation": "_resolve_llm_and_tools"},
        )
        return llm, []

    raise ModelGatewayError(
        f"Modèle défaut indisponible : {result.reason}"
    )


def _compile_orchestration_graph(subgraph_agent, checkpointer, store):
    """Assemble le graphe parent d'orchestration et le compile.

    Délègue à compile_main_graph (même module) — conservé comme
    point d'extension nommé pour la lisibilité de _build_agent.
    """
    return compile_main_graph(subgraph_agent, checkpointer, store)  # §48


def _build_agent(model_name):
    """Construit une instance d'agent — facteur commun (graphe V7)."""
    # Checkpointer SQLite officiel — persistance du thread state (§7)
    # UNIQUE, porté par le graphe parent. Partage entre instances
    # (une seule connexion, check_same_thread=False).
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(
            CHECKPOINTS_DB_PATH, check_same_thread=False
        )
    checkpointer = SqliteSaver(_conn)

    # Store longue durée officiel — User Memory cross-thread (§6)
    store = get_store()

    effective = model_name or MODEL_NAME
    if model_name is not None:
        log_event(
            "DATABASE_INIT",
            message=f"Agent instance for model={effective} (ModelSelector)",
        )
    else:
        log_event(
            "DATABASE_INIT",
            message=f"SqliteSaver checkpointer on {CHECKPOINTS_DB_PATH} | model={MODEL_NAME}",
        )

    subgraph = _build_subgraph_agent(model_name)
    return _compile_orchestration_graph(subgraph, checkpointer, store)


__all__ = [
    "CustomAgentState",
    "MainState",
    "compile_main_graph",
    "get_agent",
    "build_graph",
    "all_tools",
]
