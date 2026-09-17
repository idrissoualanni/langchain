# Graph V5 — assemblage de l'agent (§63).
#
# Ce module CONNECTE uniquement : model, tools, checkpointer,
# store, middleware, state/context schemas. Aucune logique de
# routing/knowledge/prompt ici (tout est dans les couches métier).
import sqlite3

from langchain.agents import create_agent
from langchain_ollama import ChatOllama
from langgraph.checkpoint.sqlite import SqliteSaver

from app.agent.memory import get_store
from app.config import (
    CHECKPOINTS_DB_PATH,
    MODEL_NAME,
    OLLAMA_HOST,
    ollama_headers,
)
from app.agent.middleware import build_middleware_stack
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.state import CustomAgentState
from app.agent.tools import all_tools
from app.context.schemas import AgentContext
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

    "model" : modele Ollama optionnel (ModelSelector assistant-ui).
    None/"" ou modele par defaut -> instance par defaut (MODEL_NAME).
    """
    global _conn, _agent

    if model:
        model = str(model).strip()
        if model == MODEL_NAME:
            model = None
        else:
            cached = _agents_by_model.get(model)
            if cached is not None:
                return cached
            agent = _build_agent(model)
            _agents_by_model[model] = agent
            return agent

    if _agent is not None:
        return _agent
    _agent = _build_agent(None)
    return _agent


def _build_agent(model_name):
    """Construit une instance d'agent — facteur commun."""
    headers = ollama_headers()
    llm = ChatOllama(
        model=model_name or MODEL_NAME,
        base_url=OLLAMA_HOST,
        temperature=0,
        client_kwargs={"headers": headers} if headers else None,
    )

    # Checkpointer SQLite officiel — persistance du thread state (§7)
    # Partage entre instances (une seule connexion, check_same_thread
    # =False — inchangé par la mission).
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

    return create_agent(
        model=llm,
        tools=all_tools,
        system_prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
        store=store,
        state_schema=CustomAgentState,
        context_schema=AgentContext,  # Runtime Context natif (§4)
        middleware=build_middleware_stack(),
    )
