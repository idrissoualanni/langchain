# State LangGraph de l'agent
import operator
from typing import Annotated

from langgraph.graph import MessagesState
from pydantic import Field


class CustomAgentState(MessagesState):
    """State persisté par le checkpointer SQLite.

    messages            : historique conversation (géré par LangGraph)
    user_id            : utilisateur propriétaire du thread
    interaction_count  : nombre d'interactions dans ce thread

    V5.2 — Activité pédagogique en cours (thread-local, §14-§16) :
    learning_activity  : exercice/quiz/vérification de compréhension
    actif DANS CE THREAD. Persisté par le checkpointer → un backend
    redémarré retrouve l'activité en attente de réponse. Jamais
    transféré vers un autre thread ni vers la User Memory.
    activity_log       : journal borné des événements d'activité de
    ce thread (ACTIVITY_*/QUIZ_*/CODE_*), consommé par le frontend.
    """

    user_id: str = Field(default="")
    interaction_count: int = 0

    # V5.2 — tools pédagogiques interactifs (brief §14/§19)
    learning_activity: dict = Field(default_factory=dict)
    activity_log: Annotated[list, operator.add] = Field(
        default_factory=list
    )
    # V5.2 — pratique du code : compteur d'exécutions du thread
    # (anti-abus de la sandbox, §27)
    code_runs: int = 0
