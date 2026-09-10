import os
import uuid
import logging
from pathlib import Path

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import MessagesState
from pydantic import Field

import ollama


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

OLLAMA_HOST = os.getenv(
    "OLLAMA_HOST",
    "http://localhost:11434"
)

OLLAMA_API_KEY = os.getenv(
    "OLLAMA_API_KEY"
)

MODEL_NAME = os.getenv(
    "MODEL_OLLAMA",
    "qwen2.5"
)

BASE_DIR = Path(__file__).resolve().parent

DATABASE_DIR = BASE_DIR / "database"
DATABASE_DIR.mkdir(exist_ok=True)

DB_PATH = DATABASE_DIR / "checkpoints.db"

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOG_PATH = LOG_DIR / "agent.log"


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(name)s | "
        "%(message)s"
    ),
    handlers=[
        logging.FileHandler(
            LOG_PATH,
            encoding="utf-8"
        ),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("agent")


# ============================================================
# OLLAMA
# ============================================================

client_kwargs = {}

if OLLAMA_API_KEY:
    client_kwargs["headers"] = {
        "Authorization": f"Bearer {OLLAMA_API_KEY}"
    }

llm = ChatOllama(
    model=MODEL_NAME,
    base_url=OLLAMA_HOST,
    temperature=0,
    client_kwargs=(
        client_kwargs
        if client_kwargs
        else None
    )
)


# ============================================================
# STATE
# ============================================================

class CustomAgentState(MessagesState):

    user_id: str = Field(
        default_factory=lambda: str(uuid.uuid4())
    )

    interaction_count: int = 0


# ============================================================
# TOOLS
# ============================================================

@tool
def additionner(
    a: float,
    b: float
) -> float:
    """Additionne deux nombres."""

    logger.info(
        "TOOL_START | additionner | a=%s | b=%s",
        a,
        b
    )

    result = a + b

    logger.info(
        "TOOL_END | additionner | result=%s",
        result
    )

    return result


@tool
def calculer_longueur_texte(
    texte: str
) -> int:
    """Calcule le nombre de caractères."""

    logger.info(
        "TOOL_START | calculer_longueur_texte"
    )

    result = len(texte)

    logger.info(
        "TOOL_END | longueur=%s",
        result
    )

    return result


@tool
def recherche_web(
    query: str,
    max_results: int = 3
) -> str:
    """Effectue une recherche web avec Ollama."""

    logger.info(
        "TOOL_START | recherche_web | query=%s",
        query
    )

    if not OLLAMA_API_KEY:
        logger.warning(
            "WEB_SEARCH | API key absente"
        )

        return (
            "Recherche web indisponible : "
            "OLLAMA_API_KEY non configurée."
        )

    try:

        results = ollama.web_search(
            query=query,
            max_results=max_results
        )

        output = []

        for result in results.results:

            output.append(
                f"{result.title} — "
                f"{result.url}\n"
                f"{result.content[:500]}"
            )

        logger.info(
            "TOOL_END | recherche_web | results=%s",
            len(output)
        )

        return "\n\n".join(output)

    except Exception as exc:

        logger.exception(
            "WEB_SEARCH_ERROR"
        )

        return (
            f"Erreur recherche web : {exc}"
        )


tools = [
    additionner,
    calculer_longueur_texte,
    recherche_web
]


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
Tu es un tuteur spécialisé en Python.

Ton rôle :

- expliquer clairement Python ;
- aider à corriger les erreurs ;
- fournir du code propre ;
- expliquer ton raisonnement de manière pédagogique ;
- utiliser les tools quand ils sont nécessaires.

Utilise additionner pour les calculs lorsque
l'utilisateur demande explicitement son utilisation.

Utilise calculer_longueur_texte pour les demandes
concernant le nombre de caractères.

Utilise recherche_web pour les informations
récentes ou lorsque l'utilisateur demande une recherche web.

Ne prétends jamais avoir utilisé un outil si ce n'est pas le cas.
"""


# ============================================================
# SQLITE CHECKPOINTER
# ============================================================

logger.info(
    "DATABASE_INIT | path=%s",
    DB_PATH
)

checkpointer = SqliteSaver.from_conn_string(
    str(DB_PATH)
)


# ============================================================
# AGENT
# ============================================================

agent = create_agent(
    model=llm,
    tools=tools,
    system_prompt=SYSTEM_PROMPT,
    checkpointer=checkpointer,
    state_schema=CustomAgentState
)


# ============================================================
# EXECUTION
# ============================================================

def executer_agent(
    requete: str,
    user_id: str,
    thread_id: str
):

    logger.info(
        "RUN_START | user_id=%s | thread_id=%s",
        user_id,
        thread_id
    )

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    # --------------------------------------------------------
    # Récupération de l'état existant
    # --------------------------------------------------------

    previous_state = agent.get_state(
        config
    )

    current_values = (
        previous_state.values
        if previous_state
        else {}
    )

    interaction_count = (
        current_values.get(
            "interaction_count",
            0
        ) + 1
    )

    logger.info(
        "STATE_LOAD | thread_id=%s | interaction=%s",
        thread_id,
        interaction_count
    )

    # --------------------------------------------------------
    # Input
    # --------------------------------------------------------

    input_state = {
        "messages": [
            {
                "role": "user",
                "content": requete
            }
        ],
        "user_id": user_id,
        "interaction_count": interaction_count,
    }

    logger.info(
        "USER_MESSAGE | %s",
        requete
    )

    # --------------------------------------------------------
    # AGENT
    # --------------------------------------------------------

    try:

        result = agent.invoke(
            input_state,
            config=config
        )

    except Exception:

        logger.exception(
            "AGENT_ERROR | thread_id=%s",
            thread_id
        )

        raise

    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    messages = result.get(
        "messages",
        []
    )

    last_message = messages[-1]

    response_content = (
        last_message.content
        if hasattr(
            last_message,
            "content"
        )
        else str(last_message)
    )

    logger.info(
        "ASSISTANT_MESSAGE | %s",
        response_content
    )

    logger.info(
        "RUN_END | user_id=%s | thread_id=%s",
        user_id,
        thread_id
    )

    return {
        "response": response_content,
        "thread_id": thread_id,
        "user_id": user_id,
        "interaction_count": interaction_count,
    }


# ============================================================
# DEBUG STATE
# ============================================================

def obtenir_state(thread_id: str):

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    snapshot = agent.get_state(
        config
    )

    if not snapshot:
        return None

    return snapshot.values


# ============================================================
# HISTORIQUE DES CHECKPOINTS
# ============================================================

def obtenir_historique(thread_id: str):

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    history = []

    for snapshot in agent.get_state_history(
        config
    ):

        history.append({
            "checkpoint_id": (
                snapshot.config
                .get("configurable", {})
                .get("checkpoint_id")
            ),
            "values": snapshot.values
        })

    return history


# ============================================================
# TEST LOCAL
# ============================================================

if __name__ == "__main__":

    user_id = input(
        "User ID : "
    ).strip()

    if not user_id:
        user_id = str(uuid.uuid4())

    thread_id = input(
        "Thread ID : "
    ).strip()

    if not thread_id:
        thread_id = str(uuid.uuid4())

    print()
    print(
        f"User ID   : {user_id}"
    )

    print(
        f"Thread ID : {thread_id}"
    )

    print(
        "\nTape 'exit' pour quitter."
    )

    while True:

        question = input(
            "\nVous > "
        ).strip()

        if question.lower() in {
            "exit",
            "quit"
        }:
            break

        if not question:
            continue

        try:

            result = executer_agent(
                requete=question,
                user_id=user_id,
                thread_id=thread_id
            )

            print(
                "\nAgent > "
                + result["response"]
            )

        except Exception as exc:

            print(
                f"\nErreur : {exc}"
            )