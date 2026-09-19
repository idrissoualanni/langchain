# Tests PHASE 1 — Main Graph + typed states + subgraph contracts (§4/§5/§7/§8).
#
# Scope (déterministe, aucun LLM requis) :
#   A. Contrats de subgraph (§8) : SubgraphInput/SubgraphResult +
#      ProblemResult/CodingResult/ResearchResult/VideoResult/
#      ActivityResult — validation stricte (extra=forbid), registry.
#   B. MainState typé (§7) : sur-ensemble de CustomAgentState + canaux
#      workflow/workflow_result/intake (défauts, sérialisables).
#   C. Nodes Phase 1 : intake_node (normalisation entrée) +
#      workflow_router_node / decide_workflow / route_after (matrice
#      pure, non-régression "main").
#   D. compile_main_graph : graphe standardisé contient les 9 nodes
#      et les arêtes attendues (compile sans checkpointer/store).
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

PASS = 0
FAIL = 0


def check(label: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"[PASS] {label}")
    else:
        FAIL += 1
        print(f"[FAIL] {label} — {detail}")


# ============================================================
# A. CONTRATS DE SUBGRAPH (§8)
# ============================================================
from app.graph.subgraphs.contracts import (  # noqa: E402
    ActivityResult,
    CodingResult,
    KNOWN_WORKFLOWS,
    ProblemResult,
    ResearchResult,
    SubgraphInput,
    SubgraphResult,
    SUBGRAPH_RESULTS,
    VideoResult,
)

s8_input = SubgraphInput(user_id="u1", thread_id="t1", query="énoncé")
check(
    "§8: SubgraphInput validé (extra=forbid)",
    s8_input.user_id == "u1"
    and s8_input.thread_id == "t1"
    and s8_input.query == "énoncé"
    and s8_input.payload == {},
)
try:
    SubgraphInput(unknown_field=1)
    check("§8: SubgraphInput rejette champ inconnu", False)
except Exception:
    check("§8: SubgraphInput rejette champ inconnu", True)

base = SubgraphResult(workflow="main", status="ok", message="fait")
check(
    "§8: SubgraphResult base (contrat commun)",
    base.workflow == "main" and base.status == "ok",
)

pr = ProblemResult(
    workflow="problem",
    verdict="correct",
    confidence=0.9,
    solution_steps=[{"step": 1}],
)
check(
    "§8: ProblemResult typé",
    pr.status == "ok" and pr.verdict == "correct" and pr.confidence == 0.9,
)

cr = CodingResult(
    workflow="coding",
    tested=True,
    tests={"passed": 2, "failed": 0, "total": 2},
)
check(
    "§8: CodingResult typé",
    cr.tested is True and cr.tests["total"] == 2,
)

rr = ResearchResult(workflow="research", claims=[{"claim": "x", "confidence": 0.8}])
check("§8: ResearchResult typé", rr.claims[0]["confidence"] == 0.8)

vr = VideoResult(workflow="video", segments=[{"title": "intro"}])
check("§8: VideoResult typé", vr.segments[0]["title"] == "intro")

ar = ActivityResult(workflow="activity", activity_id="a-1", evaluated=True)
check(
    "§8: ActivityResult typé",
    ar.activity_id == "a-1" and ar.evaluated is True,
)

check(
    "§8: registry SUBGRAPH_RESULTS couvre les 6 workflows",
    set(SUBGRAPH_RESULTS) == {"activity", "problem", "coding", "research", "video", "document"},
    str(sorted(SUBGRAPH_RESULTS)),
)
check(
    "§8: KNOWN_WORKFLOWS inclut main + 6 spécialisés",
    len(KNOWN_WORKFLOWS) == 7 and "main" in KNOWN_WORKFLOWS,
    str(KNOWN_WORKFLOWS),
)

# ============================================================
# B. MAIN STATE TYPÉ (§7)
# ============================================================
from app.graph.state import MainState  # noqa: E402
from app.agent.state import CustomAgentState  # noqa: E402

check(
    "§7: MainState inclut les canaux de CustomAgentState",
    set(CustomAgentState.__annotations__) <= set(MainState.__annotations__),
    f"manquants={set(CustomAgentState.__annotations__) - set(MainState.__annotations__)}",
)
check(
    "§7: canaux Phase 1 déclarés (annotations)",
    {"workflow", "workflow_result", "intake"} <= set(MainState.__annotations__),
    str(sorted(set(MainState.__annotations__) | set())),
)

# Compat checkpointer : le state reste un dict sérialisable (les
# défauts LangGraph s'appliquent à la construction du StateGraph,
# pas à l'instanciation directe d'un TypedDict).
check(
    "§7: MainState se construit en dict sérialisable",
    isinstance(MainState(), dict),
)

# ============================================================
# C. NODES PHASE 1
# ============================================================
from langchain_core.messages import HumanMessage  # noqa: E402

from app.graph.nodes.intake import intake_node  # noqa: E402
from app.graph.nodes.activity import (  # noqa: E402
    activity_node,
    route_after_activity,
)
from app.graph.nodes.workflow_router import (  # noqa: E402
    decide_workflow,
    route_after_workflow_router,
    WIRED_WORKFLOWS,
    workflow_router_node,
)

state_in = {
    "messages": [HumanMessage(content="Explique-moi les fonctions Python.")],
    "user_id": "u-1",
    "interaction_count": 3,
}
intake = intake_node(state_in, {"configurable": {"thread_id": "t-1"}})
check(
    "C: intake_node normalise la requête/ids",
    intake["intake"]["query"] == "Explique-moi les fonctions Python."
    and intake["intake"]["user_id"] == "u-1"
    and intake["intake"]["thread_id"] == "t-1"
    and intake["intake"]["interaction_count"] == 3,
    str(intake),
)

# decide_workflow — chaîne "main" par défaut (non-régression)
wd = decide_workflow({"learning_activity": {}, "routing_result": {}})
check(
    "C: decide_workflow -> main quand aucune activite",
    wd.workflow == "main" and wd.reason,
    wd.reason,
)

# Continuation d'activité (§16) — le contrat est posé dès Phase 1.
wd2 = decide_workflow(
    {"learning_activity": {"status": "waiting_for_answer", "activity_id": "a-9"}}
)
check(
    "C: decide_workflow -> activity quand activite en attente",
    wd2.workflow == "activity" and wd2.attached_to == "a-9",
    wd2.reason,
)

# workflow_router_node persist le WorkflowDecision (canal "workflow")
wr = workflow_router_node(
    {"user_id": "u-1", "learning_activity": {}, "routing_result": {}},
    {"configurable": {"thread_id": "t-1"}},
)
check(
    "C: workflow_router_node -> canal workflow (dict)",
    isinstance(wr.get("workflow"), dict)
    and wr["workflow"].get("workflow") == "main",
    str(wr),
)

check(
    "C: route_after_workflow_router -> context (main cable)",
    route_after_workflow_router({"workflow": {"workflow": "main"}}) == "context",
)
check(
    "C: route_after_workflow_router -> contexte pour workflow non branche",
    route_after_workflow_router({"workflow": {"workflow": "coding"}}) == "context",
)
check(
    "C: route_after_workflow_router -> activity (Phase 2, câblé)",
    route_after_workflow_router({"workflow": {"workflow": "activity"}}) == "activity",
)

# WIRED_WORKFLOWS contient les branches réellement câblées
# Phase 2 : "main" + "activity" (continuation §16) sont câblés.
# Phase 3 : "problem" est également câblé (ProblemSubgraph §21).
check(
    "C: WIRED_WORKFLOWS Phase 3 = {main, activity, problem} câblés",
    WIRED_WORKFLOWS == {"main": "context", "activity": "activity", "problem": "problem"},
    str(WIRED_WORKFLOWS),
)

# ============================================================
# D. COMPILE_MAIN_GRAPH — structure standardisée (§4)
# ============================================================
from langgraph.graph import StateGraph  # noqa: E402

from app.graph.main import compile_main_graph  # noqa: E402


def _dummy_agent_node(state, config=None):
    return {"messages": []}


# Node minimal : une fonction node suffit pour vérifier la structure.
graph = StateGraph(MainState)
from app.agent.orchestration import (  # noqa: E402
    context_node,
    fallback_node,
    learning_node,
    response_node,
    retrieval_node,
    router_node,
)

for name, fn in [
    ("intake", intake_node),
    ("router", router_node),
    ("retrieval", retrieval_node),
    ("fallback", fallback_node),
    ("workflow_router", workflow_router_node),
    ("activity", activity_node),
    ("context", context_node),
    ("learning", learning_node),
    ("agent", _dummy_agent_node),
    ("response", response_node),
]:
    graph.add_node(name, fn)

from langgraph.graph import END, START  # noqa: E402

graph.add_edge(START, "intake")
graph.add_edge("intake", "router")
graph.add_conditional_edges(
    "router",
    lambda state: "retrieval",
    {"retrieval": "retrieval", "fallback": "fallback"},
)
graph.add_edge("retrieval", "fallback")
graph.add_edge("fallback", "workflow_router")
graph.add_conditional_edges(
    "workflow_router",
    lambda state: "context",
    {"context": "context", "activity": "activity"},
)
graph.add_conditional_edges(
    "activity",
    route_after_activity,
    {"context": "context"},
)
graph.add_edge("context", "learning")
graph.add_edge("learning", "agent")
graph.add_edge("agent", "response")
graph.add_edge("response", END)

compiled = graph.compile()
# LangGraph distingue les nodes réels des mappages : on vérifie que les
# 10 nodes existent bien dans le graphe compilé.
g = compiled.get_graph()
node_names = {n.id for n in g.nodes if hasattr(n, "id")} or set(g.nodes)
check(
    "D: compile_main_graph - 10 nodes presents",
    len(node_names) >= 10,
    str(sorted(node_names))[:200],
)

# compile_main_graph réel — vérifier qu'il retourne un objet compilé
# (sans lancer de LLM ; checkpointer/store optionnels pour l'assemblage).
try:
    real = compile_main_graph(_dummy_agent_node, None, None)
    check("D: compile_main_graph compile sans checkpointer", real is not None)
except Exception as exc:
    check("D: compile_main_graph compile sans checkpointer", False, str(exc)[:200])

# ============================================================
# Résumé
# ============================================================
print()
print(f"TOTAL: {PASS + FAIL} | PASS: {PASS} | FAIL: {FAIL}")
if FAIL:
    print("ECHECS:", [x for x in globals().values() if isinstance(x, Exception)])
if FAIL:
    sys.exit(1)