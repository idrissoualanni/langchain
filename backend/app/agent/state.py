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

    # V7 — orchestration LangGraph mono-graphe (mission ORCHESTRATION).
    # Canaux de résolution des nodes parent (ROUTER/RETRIEVAL/
    # FALLBACK/CONTEXT/LEARNING) — résultats de services réels
    # persistés par le checkpointer, consommés par l'aval :
    #   routing_result    : RoutingResult.model_dump()
    #   knowledge         : KnowledgeSearchResult.model_dump()
    #   web               : SearchResponse.model_dump()
    #   fallback          : FallbackDecision.model_dump()
    #   built_context     : BuiltContext.model_dump() — assemblé UNE
    #                       fois par le node CONTEXT, consommé par le
    #                       dynamic_prompt (aucune re-exécution).
    #   learning_decision : LearningDecision.model_dump()
    #   agent_response    : AgentResponse.model_dump() — contrat public
    #                       produit par le node RESPONSE, lu par le
    #                       runner (fallback au comportement historique
    #                       si absent).
    routing_result: dict = Field(default_factory=dict)
    knowledge: dict = Field(default_factory=dict)
    web: dict = Field(default_factory=dict)
    fallback: dict = Field(default_factory=dict)
    built_context: dict = Field(default_factory=dict)
    learning_decision: dict = Field(default_factory=dict)
    agent_response: dict = Field(default_factory=dict)
