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
from app.agent.middleware import ToolEventMiddleware
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.state import CustomAgentState
from app.agent.tools import all_tools
from app.logging.events import log_event

_conn: sqlite3.Connection | None = None
_agent = None


def get_agent():
    """Singleton agent — initialisé au startup FastAPI (lifespan)."""
    global _conn, _agent
    if _agent is not None:
        return _agent

    headers = ollama_headers()
    llm = ChatOllama(
        model=MODEL_NAME,
        base_url=OLLAMA_HOST,
        temperature=0,
        client_kwargs={"headers": headers} if headers else None,
    )

    # Checkpointer SQLite officiel — persistance réelle du state LangGraph
    _conn = sqlite3.connect(CHECKPOINTS_DB_PATH, check_same_thread=False)
    checkpointer = SqliteSaver(_conn)

    # Store longue durée officiel — profil utilisateur cross-thread
    store = get_store()

    log_event(
        "DATABASE_INIT",
        message=f"SqliteSaver checkpointer on {CHECKPOINTS_DB_PATH} | model={MODEL_NAME}",
    )

    _agent = create_agent(
        model=llm,
        tools=all_tools,
        system_prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
        store=store,
        state_schema=CustomAgentState,
        middleware=[ToolEventMiddleware()],
    )

    return _agent
