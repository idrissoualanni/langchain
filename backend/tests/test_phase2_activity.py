# Tests PHASE 2 — Activity domain (§14/§15/§16/§17).
#
# Scope (deterministic, no LLM, no Ollama, no live agent) :
#   A. Lifecycle §14 : lifecycle_stage map les statuts V5.2 vers les
#      etapes produit (created/completed/cancelled/feedback/in_progress).
#   B. Contrat §15 : ActivityContract (champs exacts, .lifecycle,
#      .continuable), activity_to_contract (projection state->contrat,
#      result precede last_evaluation, payload public sans fuite),
#      make_result (structure stable).
#   C. Continuation §16 : is_active_activity / is_terminal_activity /
#      continuation_target / active_from_state / next_step_hint —
#      jamais de nouvelle activite.
#   D. Store §17 : facade lecture/ecriture du channel learning_activity
#      via checkpointer UNIQUEMENT (get_agent stubbé, aucun ChatOllama).
#
# IMPOSSIBLE : app.agent.graph.get_agent() n'est JAMAIS appelé en vrai —
# app.activity.store.get_agent est réassigné vers un stub local.
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


# Statuts V5.2 importés de la source unique (activity_state, comme dans
# app/activity/schemas.py) — même style d'import.
from app.schemas.activity import (  # noqa: E402
    ACTIVITY_ABANDONED,
    ACTIVITY_CHECKING_UNDERSTANDING,
    ACTIVITY_COMPLETED,
    ACTIVITY_EVALUATING,
    ACTIVITY_GIVING_HINT,
    ACTIVITY_IDLE,
    ACTIVITY_WAITING_ANSWER,
    ACTIVITY_WAITING_RETRY,
    ACTIVITY_TYPE_EXERCISE,
    ACTIVITY_TYPE_QUIZ,
    ACTIVITY_TYPE_UNDERSTANDING_CHECK,
    ALL_ACTIVITY_STATUSES,
)

# ============================================================
# A. LIFECYCLE §14
# ============================================================
from app.schemas.activity import (  # noqa: E402
    ACTIVITY_TYPES,
    CONTINUABLE_STATUSES,
    LIFECYCLE_CANCELLED,
    LIFECYCLE_COMPLETED,
    LIFECYCLE_CREATED,
    LIFECYCLE_EVALUATING,
    LIFECYCLE_FAILED,
    LIFECYCLE_FEEDBACK,
    LIFECYCLE_IN_PROGRESS,
    LIFECYCLE_READY,
    LIFECYCLE_WAITING_ANSWER,
    TERMINAL_STATUSES,
    ActivityContract,
    activity_to_contract,
    lifecycle_stage,
    make_result,
)

_expected_continuable = frozenset(
    {
        ACTIVITY_WAITING_ANSWER,
        ACTIVITY_EVALUATING,
        ACTIVITY_GIVING_HINT,
        ACTIVITY_WAITING_RETRY,
        ACTIVITY_CHECKING_UNDERSTANDING,
    }
)
check(
    "A: §14 CONTINUABLE_STATUSES = 5 statuts V5.2",
    CONTINUABLE_STATUSES == _expected_continuable,
    str(CONTINUABLE_STATUSES),
)
check(
    "A: §14 TERMINAL_STATUSES = {completed, abandoned}",
    TERMINAL_STATUSES == frozenset(
        {ACTIVITY_COMPLETED, ACTIVITY_ABANDONED}
    ),
    str(TERMINAL_STATUSES),
)
check(
    "A: §14 ACTIVITY_TYPES = 3 types (exercise/quiz/understanding_check)",
    set(ACTIVITY_TYPES)
    == {
        ACTIVITY_TYPE_EXERCISE,
        ACTIVITY_TYPE_QUIZ,
        ACTIVITY_TYPE_UNDERSTANDING_CHECK,
    }
    and len(ACTIVITY_TYPES) == 3,
    str(ACTIVITY_TYPES),
)
check(
    "A: §14 lifecycle_stage->created (None)",
    lifecycle_stage(None) == LIFECYCLE_CREATED,
)
check(
    "A: §14 lifecycle_stage->created (idle)",
    lifecycle_stage(ACTIVITY_IDLE) == LIFECYCLE_CREATED,
)
check(
    "A: §14 lifecycle_stage->completed (completed)",
    lifecycle_stage(ACTIVITY_COMPLETED) == LIFECYCLE_COMPLETED,
)
check(
    "A: §14 lifecycle_stage->cancelled (abandoned)",
    lifecycle_stage(ACTIVITY_ABANDONED) == LIFECYCLE_CANCELLED,
)
check(
    "A: §14 lifecycle_stage->feedback (checking_understanding)",
    lifecycle_stage(ACTIVITY_CHECKING_UNDERSTANDING) == LIFECYCLE_FEEDBACK,
)
check(
    "A: §14 lifecycle_stage->in_progress (waiting_for_answer)",
    lifecycle_stage(ACTIVITY_WAITING_ANSWER) == LIFECYCLE_IN_PROGRESS,
)
check(
    "A: §14 lifecycle_stage->in_progress (evaluating)",
    lifecycle_stage(ACTIVITY_EVALUATING) == LIFECYCLE_IN_PROGRESS,
)
check(
    "A: §14 lifecycle_stage->in_progress (giving_hint)",
    lifecycle_stage(ACTIVITY_GIVING_HINT) == LIFECYCLE_IN_PROGRESS,
)
check(
    "A: §14 lifecycle_stage->in_progress (waiting_for_retry)",
    lifecycle_stage(ACTIVITY_WAITING_RETRY) == LIFECYCLE_IN_PROGRESS,
)
check(
    "A: §14 lifecycle_stage->created (status inconnu)",
    lifecycle_stage("bogus") == LIFECYCLE_CREATED,
)
check(
    "A: §14 pas de deuxieme machine (constants lifecycle exists)",
    {
        LIFECYCLE_CREATED,
        LIFECYCLE_READY,
        LIFECYCLE_IN_PROGRESS,
        LIFECYCLE_WAITING_ANSWER,
        LIFECYCLE_EVALUATING,
        LIFECYCLE_FEEDBACK,
        LIFECYCLE_COMPLETED,
        LIFECYCLE_FAILED,
        LIFECYCLE_CANCELLED,
    } == {
        "created",
        "ready",
        "in_progress",
        "waiting_for_answer",
        "evaluating",
        "feedback",
        "completed",
        "failed",
        "cancelled",
    },
)

# ============================================================
# B. CONTRAT D'ACTIVITE §15
# ============================================================
check(
    "B: §15 ActivityContract = champs exacts (14) et defauts",
    ActivityContract().activity_id == ""
    and ActivityContract().status == ACTIVITY_IDLE
    and ActivityContract().attempt_count == 0
    and ActivityContract().current_step == 0
    and ActivityContract().payload == {}
    and ActivityContract().result == {},
    str(ActivityContract()),
)
_fields = set(ActivityContract.__dataclass_fields__)
_expected_fields = {
    "activity_id",
    "thread_id",
    "user_id",
    "activity_type",
    "subject",
    "topic",
    "status",
    "created_at",
    "updated_at",
    "payload",
    "attempt_count",
    "current_step",
    "result",
}
check(
    "B: §15 ActivityContract expose exactement les 13 champs listes",
    _fields == _expected_fields,
    str(sorted(_fields)),
)

contract = ActivityContract(
    status=ACTIVITY_WAITING_ANSWER,
    subject="python",
    topic="functions",
    attempt_count=2,
)
check(
    "B: §15 .lifecycle derive du statut (in_progress)",
    contract.lifecycle == LIFECYCLE_IN_PROGRESS,
)
check(
    "B: §15 .continuable True pour waiting_for_answer",
    contract.continuable is True,
)
check(
    "B: §15 .continuable False pour statut terminal",
    ActivityContract(status=ACTIVITY_COMPLETED).continuable is False,
)

raw = {
    "activity_id": "a-1",
    "activity_type": ACTIVITY_TYPE_QUIZ,
    "subject": "python",
    "topic": "functions",
    "status": ACTIVITY_WAITING_ANSWER,
    "started_at": "2026-09-19T10:00:00Z",
    "updated_at": "2026-09-19T10:05:00Z",
    "attempts": 3,
    "question_index": 2,
    "expected_response_type": "text",
    "hint_level": 1,
    "awaiting_answer": True,
    "question": "Quelle est la difference entre args et kwargs ?",
    "expected": "les positions",
    "source": "informatique/python/functions",
}
cc = activity_to_contract(raw)
check(
    "B: §15 started_at->created_at / attempts->attempt_count",
    cc.created_at == "2026-09-19T10:00:00Z"
    and cc.attempt_count == 3,
    f"created_at={cc.created_at!r} attempt_count={cc.attempt_count}",
)
check(
    "B: §15 question_index->current_step",
    cc.current_step == 2,
    f"current_step={cc.current_step}",
)
check(
    "B: §15 thread_id/user_id injectes par l'appelant",
    activity_to_contract(raw, thread_id="t-x", user_id="u-y").thread_id
    == "t-x"
    and activity_to_contract(
        raw, thread_id="t-x", user_id="u-y"
    ).user_id
    == "u-y",
)
check(
    "B: §15 payload public = {expected_response_type, hint_level, awaiting_answer}",
    cc.payload
    == {
        "expected_response_type": "text",
        "hint_level": 1,
        "awaiting_answer": True,
    },
    str(cc.payload),
)
check(
    "B: §15 aucune fuite de la reponse attendue dans le payload",
    not {"question", "expected", "source"} & set(cc.payload),
    str(cc.payload),
)

cc_default = activity_to_contract(None)
check(
    "B: §15 activity_to_contract(None) -> statut idle + vide",
    cc_default.status == ACTIVITY_IDLE
    and cc_default.activity_id == ""
    and cc_default.payload == {}
    and cc_default.result == {},
)
check(
    "B: §15 activity_to_contract({}) -> statut idle (defaut)",
    activity_to_contract({}).status == ACTIVITY_IDLE,
)

cc_result = activity_to_contract(
    {
        "status": ACTIVITY_COMPLETED,
        "result": {"verdict": "correct"},
        "last_evaluation": {"verdict": "wrong"},
    }
)
check(
    "B: §15 result precede last_evaluation",
    cc_result.result.get("verdict") == "correct",
    str(cc_result.result),
)

res = make_result(
    score=0.8,
    verdict="correct",
    strengths=["exact", 7],
    weaknesses=["short"],
    feedback="tout passe",
    evidence=[{"line": 3}],
    confidence=0.9,
)
check(
    "B: §15 make_result structure stable (7 cles)",
    set(res.keys())
    == {"score", "verdict", "strengths", "weaknesses", "feedback",
        "evidence", "confidence"}
    and res["score"] == 0.8
    and res["verdict"] == "correct"
    and res["strengths"] == ["exact", "7"]
    and res["weaknesses"] == ["short"]
    and res["feedback"] == "tout passe"
    and res["evidence"] == [{"line": 3}]
    and res["confidence"] == 0.9,
    str(res),
)
res_default = make_result(score=None, verdict="correct", strengths=[], weaknesses=[], feedback="ok")
check(
    "B: §15 make_result defauts (evidence=[] confidence=1.0 score=None)",
    res_default["score"] is None
    and res_default["evidence"] == []
    and res_default["confidence"] == 1.0,
    str(res_default),
)

# ============================================================
# C. CONTINUATION §16
# ============================================================
from app.activity.continuation import (  # noqa: E402
    active_from_state,
    continuation_target,
    is_active_activity,
    is_terminal_activity,
    next_step_hint,
)

_check_active = {
    ACTIVITY_WAITING_ANSWER: True,
    ACTIVITY_EVALUATING: True,
    ACTIVITY_GIVING_HINT: True,
    ACTIVITY_WAITING_RETRY: True,
    ACTIVITY_CHECKING_UNDERSTANDING: True,
    ACTIVITY_IDLE: False,
    ACTIVITY_COMPLETED: False,
    ACTIVITY_ABANDONED: False,
    "unknown": False,
    None: False,
    "": False,
}
for _st, _want in _check_active.items():
    _act = {"status": _st, "activity_id": "a-1"} if isinstance(_st, str) else _st
    check(
        f"C: §16 is_active_activity -> {_want} (statut {_st!r})",
        is_active_activity(_act) is _want,
        f"status={_st!r} result={is_active_activity(_act)}",
    )

check(
    "C: §16 is_active_activity False pour {} / None / non-dict",
    is_active_activity({}) is False
    and is_active_activity(None) is False
    and is_active_activity("spam") is False,
)

for _st, _want in [(ACTIVITY_COMPLETED, True), (ACTIVITY_ABANDONED, True),
                   (ACTIVITY_IDLE, False), (ACTIVITY_WAITING_ANSWER, False),
                   (None, False)]:
    _act = {"status": _st} if isinstance(_st, str) else _st
    check(
        f"C: §16 is_terminal_activity -> {_want} (statut {_st!r})",
        is_terminal_activity(_act) is _want,
    )

check(
    "C: §16 continuation_target -> activity (waiting_for_answer)",
    continuation_target({"status": ACTIVITY_WAITING_ANSWER}) == "activity",
)
check(
    "C: §16 continuation_target -> main (idle/completed/None/empty)",
    continuation_target({"status": ACTIVITY_IDLE}) == "main"
    and continuation_target({"status": ACTIVITY_COMPLETED}) == "main"
    and continuation_target({"status": "unknown"}) == "main"
    and continuation_target(None) == "main"
    and continuation_target({}) == "main",
)

values_active = {"learning_activity": {"status": ACTIVITY_WAITING_ANSWER, "activity_id": "a-7"}}
check(
    "C: §16 active_from_state -> activite en cours",
    active_from_state(values_active)["activity_id"] == "a-7",
)
check(
    "C: §16 active_from_state -> {} si inactive / absente / non-dict",
    active_from_state({"learning_activity": {"status": ACTIVITY_IDLE}}) == {}
    and active_from_state({"learning_activity": {"status": ACTIVITY_COMPLETED}}) == {}
    and active_from_state({}) == {}
    and active_from_state(None) == {}
    and active_from_state({"learning_activity": "spam"}) == {},
)

_hint_cases = [
    (ACTIVITY_WAITING_ANSWER, "evaluate"),
    (ACTIVITY_EVALUATING, "finalize"),
    (ACTIVITY_GIVING_HINT, "hint"),
    (ACTIVITY_WAITING_RETRY, "retry"),
    (ACTIVITY_CHECKING_UNDERSTANDING, "understand"),
]
for _st, _kind in _hint_cases:
    _hint = next_step_hint({"status": _st, "activity_id": "a-1"})
    check(
        f"C: §16 next_step_hint -> {_kind} (statut {_st})",
        _hint.get("kind") == _kind
        and _hint.get("status") == _st
        and bool(_hint.get("detail")),
        str(_hint),
    )
check(
    "C: §16 next_step_hint -> none si inactif",
    next_step_hint({"status": ACTIVITY_IDLE})["kind"] == "none"
    and next_step_hint(None)["kind"] == "none"
    and next_step_hint({})["kind"] == "none",
    str(next_step_hint({"status": ACTIVITY_IDLE})),
)
_check_kinds = [next_step_hint({"status": s, "activity_id": "a"})["kind"]
               for s in ALL_ACTIVITY_STATUSES if s != ACTIVITY_IDLE]
check(
    "C: §16 kind jamais 'create/new' (aucune nouvelle activite)",
    all(k in {"evaluate", "finalize", "hint", "retry", "understand", "none"}
        for k in _check_kinds),
    str(_check_kinds),
)

# ============================================================
# D. STORE §17 — facade checkpointer, get_agent stubbé
# ============================================================
class StubSnapshot:
    def __init__(self, values):
        self.values = values


class StubAgent:
    def __init__(self, values=None, raise_on_get=False):
        self.values = values if values is not None else {}
        self.raise_on_get = raise_on_get
        self.saved = []

    def get_state(self, config):
        if self.raise_on_get:
            raise RuntimeError("boom")
        return StubSnapshot(dict(self.values))

    def update_state(self, config, values, **kwargs):
        self.saved.append((dict(values), dict(kwargs)))
        return {"checkpoint_id": "ckpt-stub"}


import app.activity.store as store_mod  # noqa: E402
from app.activity.store import ACTIVITY_CHANNEL  # noqa: E402

_stub = StubAgent(
    {
        ACTIVITY_CHANNEL: {
            "activity_id": "a-77",
            "activity_type": ACTIVITY_TYPE_EXERCISE,
            "subject": "python",
            "topic": "loops",
            "status": ACTIVITY_WAITING_ANSWER,
            "attempts": 1,
        },
        "activity_log": [],
    }
)
store_mod.get_agent = lambda: _stub  # jamais ChatOllama ici

_activity = store_mod.get_activity("u-1", "t-1")
check(
    "D: §17 get_activity lit le channel learning_activity (stub)",
    isinstance(_activity, dict) and _activity.get("activity_id") == "a-77",
    str(_activity),
)

_cc = store_mod.get_activity_contract("u-1", "t-1")
check(
    "D: §17 get_activity_contract projette (id/subject/status/thread)",
    _cc.activity_id == "a-77"
    and _cc.subject == "python"
    and _cc.thread_id == "t-1"
    and _cc.user_id == "u-1"
    and _cc.status == ACTIVITY_WAITING_ANSWER,
    str(_cc),
)
check(
    "D: §17 has_continuable_activity True (waiting_for_answer)",
    store_mod.has_continuable_activity("u-1", "t-1") is True,
)

_stub_done = StubAgent({ACTIVITY_CHANNEL: {"status": ACTIVITY_COMPLETED}})
store_mod.get_agent = lambda: _stub_done
check(
    "D: §17 has_continuable_activity False (completed)",
    store_mod.has_continuable_activity("u-1", "t-1") is False,
)
_stub_idle = StubAgent({ACTIVITY_CHANNEL: {"status": ACTIVITY_IDLE}})
store_mod.get_agent = lambda: _stub_idle
check(
    "D: §17 has_continuable_activity False (idle)",
    store_mod.has_continuable_activity("u-1", "t-1") is False,
)
_stub_missing = StubAgent({})
store_mod.get_agent = lambda: _stub_missing
check(
    "D: §17 get_activity -> {} (aucune activite)",
    store_mod.get_activity("u-1", "t-1") == {},
)
check(
    "D: §17 get_activity_contract -> idle par defaut (aucune activite)",
    store_mod.get_activity_contract("u-1", "t-1").status == ACTIVITY_IDLE,
)
check(
    "D: §17 has_continuable_activity False (channel absent)",
    store_mod.has_continuable_activity("u-1", "t-1") is False,
)

_stub_boom = StubAgent({}, raise_on_get=True)
store_mod.get_agent = lambda: _stub_boom
check(
    "D: §17 get_activity -> {} si checkpointer en erreur (non-bloquant)",
    store_mod.get_activity("u-1", "t-1") == {},
)

_stub_save = StubAgent({})
store_mod.get_agent = lambda: _stub_save
check(
    "D: §17 save_activity ecrit via update_state (checkpointer)",
    store_mod.save_activity("u-1", "t-1", {"status": ACTIVITY_WAITING_ANSWER, "activity_id": "a-9"})
    is True
    and len(_stub_save.saved) == 1
    and _stub_save.saved[0][0] == {ACTIVITY_CHANNEL: {"status": ACTIVITY_WAITING_ANSWER, "activity_id": "a-9"}},
    str(_stub_save.saved),
)
check(
    "D: §17 clear_activity ramene le channel a idle",
    store_mod.clear_activity("u-1", "t-1") is True
    and _stub_save.saved[-1][0] == {ACTIVITY_CHANNEL: {"status": ACTIVITY_IDLE, "activity_id": ""}},
    str(_stub_save.saved),
)
_stub_log = StubAgent({"activity_log": [{"event": "A"}, {"event": "B"}, {"event": "C"}]})
store_mod.get_agent = lambda: _stub_log
check(
    "D: §17 activity_log lit le channel activity_log",
    [e["event"] for e in store_mod.activity_log("u-1", "t-1")] == ["A", "B", "C"],
)
store_mod.get_agent = lambda: StubAgent({})
check(
    "D: §17 activity_log -> [] si log absent",
    store_mod.activity_log("u-1", "t-1") == [],
)

# ============================================================
# Resume
# ============================================================
print()
print(f"TOTAL: {PASS + FAIL} | PASS: {PASS} | FAIL: {FAIL}")
if FAIL:
    print("ECHECS:", [x for x in globals().values() if isinstance(x, Exception)])
if FAIL == 0:
    print("TESTS PHASE 2 ACTIVITY: OK")
else:
    print("TESTS PHASE 2 ACTIVITY: ECHEC")
if FAIL:
    sys.exit(1)