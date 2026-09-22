# Main Graph State — états typés de l'orchestration (§7 mission refactor).
#
# Fusion refactor :
#   - CustomAgentState (ex app/agent/state.py) : state persisté par le
#     checkpointer SQLite — messages + canaux d'orchestration V7 ;
#   - MainState (ex app/graph/state.py) : sur-ensemble typé du Main
#     Graph — ajoute les canaux de routage de workflow (Phase 1).
#
# MainState étend CustomAgentState (MessagesState) sans re-créer un
# système parallèle : il reste compatible avec le checkpointer
# SqliteSaver et le sous-graphe create_agent (même schéma partagé).
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


class MainState(CustomAgentState):
    """State typé du Main Graph (§7) — sur-ensemble de CustomAgentState.

    MessagesState (hérité) + canaux d'orchestration V7 + canaux
    de routage de workflow (Phase 1). Les nodes parent du Main Graph
    (INTAKE → ROUTER → WORKFLOW_ROUTER → CONTEXT → LEARNING → AGENT →
    RESPONSE) lisent/écrivent ces canaux via le checkpointer.

    Canaux ajoutés en Phase 1 :
      workflow        : WorkflowDecision.model_dump() — décision de
                        routage vers un workflow (main/activity/...)
                        émise par le node WORKFLOW_ROUTER.
      workflow_result : SubgraphResult.model_dump() — résultat structuré
                        produit par UN subgraph (§8) quand un workflow
                        en exécute un (Phases 2-7). Présent dès la Phase 1
                        pour fixer le contrat, toujours dict vide sinon.
      payload         : entrée STRUCTURÉE d'un workflow (§8 SubgraphInput)
                        — research_mode (deep-research/academic-search/
                        news-search), source vidéo (filename/source_url)…
                        Canal d'ENTRÉE écrit par le runner depuis le
                        composer, consommé par les nodes subgraph.
    """

    # --- Phase 1 : routage de workflow (§4/§5/§8) ---
    intake: dict = Field(
        default_factory=dict,
        description="Entrée normalisée du run (INTAKE) : "
        "{query, user_id, thread_id, interaction_count}",
    )
    workflow: dict = Field(
        default_factory=dict,
        description="WorkflowDecision.model_dump() — décision émise "
        "par WORKFLOW_ROUTER",
    )
    workflow_result: dict = Field(
        default_factory=dict,
        description="SubgraphResult.model_dump() — résultat structuré "
        "produit par UN subgraph (§8), vide en Phase 1",
    )
    workflow_hint: str = Field(
        default="",
        description="Hint de workflow émis par le composer (@mention "
        "→ terme). Canal d'ENTRÉE consommé par WORKFLOW_ROUTER — "
        "validation contre KNOWN_WORKFLOWS, inconnu → ignoré + tracé.",
    )
    payload: dict = Field(
        default_factory=dict,
        description="Entrée structurée d'un workflow (§8 SubgraphInput) : "
        "research_mode (deep-research/academic-search/news-search), "
        "source vidéo (filename/source_url/duration). Canal d'ENTRÉE "
        "écrit par le runner, consommé par les nodes subgraph.",
    )


__all__ = ["CustomAgentState", "MainState"]
