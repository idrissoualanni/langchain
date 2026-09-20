# Graph V7 — assemblage du graphe d'orchestration unique (§63).
#
# Mission ORCHESTRATION : ce module connecte UNIQUEMENT — model,
# tools, checkpointer, store, middleware, state/context schemas et
# les NODES d'orchestration. Toute la logique métier vit dans les
# couches (router/fallback/builder/learning/normalizer), appelée
# RÉELLEMENT par les nodes (app.agent.orchestration, §48).
#
# PHASE 1 (§4/§83) : l'ASSEMBLAGE standardisé vit désormais dans
# app.graph.main (compile_main_graph, sur MainState) — ce module
# fournit la FACTORY d'agent (model/tools/checkpointer/store) et
# délègue l'assemblage. Graphe Phase 1 :
#
#   START → INTAKE → ROUTER →[retrieval|fallback] → FALLBACK →
#   WORKFLOW_ROUTER →[main]→ CONTEXT → LEARNING → AGENT →
#   RESPONSE → END
#
# Défense d'un checkpointer UNIQUE : le sous-graphe create_agent
# est compilé SANS checkpointer ni store — il HÉRITE ceux du graphe
# parent (POC-3 validé : get_state/get_state_history fonctionnent,
# tables checkpoints/writes créées par le parent). state_schema et
# context_schema sont partagés → request.state du middleware expose
# built_context/learning_decision (POC-2).
import sqlite3

from langchain.agents import create_agent
from langgraph.checkpoint.sqlite import SqliteSaver

from app.agent.memory import get_store
from app.config import CHECKPOINTS_DB_PATH, MODEL_NAME
from app.agent.middleware import build_middleware_stack
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.state import CustomAgentState

# Import direct depuis tools.py (le fichier) pour éviter le cycle avec le package
from app.agent import tools as tools_module

all_tools = tools_module.all_tools
from app.context.schemas import AgentContext
from app.graph.main import compile_main_graph
from app.logging.events import log_event

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
            from app.models.registry import (
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


def _build_subgraph_agent(model_name):
    """Sous-graphe AGENT (create_agent) — SANS checkpointer ni store.

    Le thread state est persisté par le CHECKPOINTER UNIQUE du
    graphe parent (POC-3) : le sous-graphe hérite le checkpointer
    de son contexte d'exécution. Le store long terme est un
    singleton module (app.agent.memory.get_store) — pas besoin de
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
    from app.models.gateway import (
        ModelGatewayError,
        create_llm_from_config,
        get_llm_for_purpose,
    )
    from app.models.registry import find_model_config
    from app.models.resolver import resolve_model_for_purpose

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

    Phase 1 (§4/§83) : délègue à compile_main_graph (app.graph.main)
    — SHIM rétrocompatible. Le graphe standardisé ajoute les nodes
    INTAKE et WORKFLOW_ROUTER (canaux workflow/workflow_result de
    MainState) sans changer la chaîne métier
    (ROUTER→RETRIEVAL/FALLBACK→CONTEXT→LEARNING→AGENT→RESPONSE).
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