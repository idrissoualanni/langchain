# State LangGraph de l'agent
from langgraph.graph import MessagesState
from pydantic import Field


class CustomAgentState(MessagesState):
    """State persisté par le checkpointer SQLite.

    messages            : historique conversation (géré par LangGraph)
    user_id            : utilisateur propriétaire du thread
    interaction_count  : nombre d'interactions dans ce thread
    """

    user_id: str = Field(default="")
    interaction_count: int = 0
