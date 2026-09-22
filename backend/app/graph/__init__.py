# Graph (Phase 1) — Main Graph, typed states et contrats de subgraphs.
#
# Cible §83 : graph/main.py assemble le Main Graph ; graph/state.py
# porte MainState (état typé du Main Graph, §7) ; graph/subgraphs/
# porte les contrats structurés d'entrée/sortie des subgraphs (§5/§8
# — ProblemResult, CodingResult, ResearchResult, VideoResult,
# ActivityResult). Le sous-graphe agentique `create_agent` reste dans
# app/agent (il EST le sous-graphe conversationnel, §5).
#
# Phase 1 = STANDARDISER, pas recréer : l'assemblage existant
# (app/agent/graph.py) délègue à compile_main_graph (app/graph/main.py)
# — mêmes nodes métier (app.agent.orchestration), mêmes services,
# même checkpointer/store. Seuls INTAKE et WORKFLOW_ROUTER sont
# ajoutés (nouveaux nodes, non-cassants).
from app.graph.main.state import MainState
from app.schemas.workflow import (
    ActivityResult,
    CodingResult,
    ProblemResult,
    ResearchResult,
    SubgraphInput,
    SubgraphResult,
    VideoResult,
)

__all__ = [
    "MainState",
    "SubgraphInput",
    "SubgraphResult",
    "ProblemResult",
    "CodingResult",
    "ResearchResult",
    "VideoResult",
    "ActivityResult",
]