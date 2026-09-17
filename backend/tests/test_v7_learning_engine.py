# Tests V7 — LEARNING ENGINE (§42-§45).
#
# §42 : 14 scénarios de décision (profil inexistant, zones mastery,
#        confidence, weak point, régression, progression, goal,
#        activity, ambiguous, knowledge absent, isolation, cross-thread)
# §43 : conflits de règles (priorité documentée)
# §44 : stabilité — same context → same decision
# §45 : intégration LLM réelle (serveur, logs LEARNING_DECISION)
#
# Parties A-C : UNITAIRES (aucun serveur requis) — décide() sur
# des BuiltContext construits directs + profils réels semés.
# Partie D : INTÉGRATION LLM réel (serveur BASE_PORT requis).
import os
import sys
import uuid

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


from app.context.schemas import (  # noqa: E402
    ActivityContextInfo,
    BuiltContext,
    KnowledgeSearchResult,
    RoutingResult,
)
from app.learning.decision import (  # noqa: E402
    ACTIVITY_TRANSITIONS,
    LearningDecision,
)
from app.learning.engine import decide  # noqa: E402
from app.learning.learning_profile import (  # noqa: E402
    create_learning_goal,
    update_profile_from_observation,
)
from app.learning.schemas import (  # noqa: E402
    LearningContextInfo,
    LearningObservation,
)
from app.learning.rules import (  # noqa: E402
    MASTERY_THRESHOLDS,
    mastery_zone,
    read_trajectory,
)

K_FOUND = KnowledgeSearchResult(status="found")
K_EMPTY = KnowledgeSearchResult(status="unavailable")


def make_ctx(**kw) -> BuiltContext:
    """BuiltContext de test — routing supported python/functions
    + knowledge found par défaut (surcharge possible)."""
    base = dict(
        routing=RoutingResult(
            status="supported",
            subject="python",
            topic="functions",
            confidence=0.9,
        ),
        knowledge=K_FOUND,
    )
    base.update(kw)
    return BuiltContext(**base)


def act(status="waiting_for_answer", **kw):
    kw.setdefault("activity_id", "a1")
    kw.setdefault("activity_type", "exercise")
    kw.setdefault("status", status)
    kw.setdefault("subject", "python")
    kw.setdefault("topic", "functions")
    return ActivityContextInfo(**kw)


def lci(**kw):
    kw.setdefault("status", "active")
    kw.setdefault("subject", "python")
    kw.setdefault("topic", "functions")
    return LearningContextInfo(**kw)


# ==================================================================
print("\n--- §6/§12 : zones de maîtrise ---")
# ==================================================================

check(
    "Z1: seuils nommés (weak .40 / developing .70 / proficient .85)",
    MASTERY_THRESHOLDS["weak"] == 0.40
    and MASTERY_THRESHOLDS["developing"] == 0.70
    and MASTERY_THRESHOLDS["proficient"] == 0.85,
)
check(
    "Z2: mastery_zone couvre les 4 zones + unknown",
    mastery_zone(0.30) == "weak"
    and mastery_zone(0.50) == "developing"
    and mastery_zone(0.75) == "proficient"
    and mastery_zone(0.90) == "strong"
    and mastery_zone(None) == "unknown",
)

print("\n--- §11 : trajectoire ---")
check("T1: 0.30→0.42→0.58 = progression",
      read_trajectory([0.30, 0.42, 0.58]) == "progression")
check("T2: 0.72→0.70→0.69→0.65 = régression",
      read_trajectory([0.72, 0.70, 0.69, 0.65]) == "regression")
check("T3: 0.50→0.52→0.51 = plateau",
      read_trajectory([0.50, 0.52, 0.51]) == "plateau")
check("T4: <2 scores = unknown (pas inventé)",
      read_trajectory([0.5]) == "unknown"
      and read_trajectory([]) == "unknown"
      and read_trajectory([None, None]) == "unknown")

# ==================================================================
print("\n--- §42 : scénarios de décision ---")
# ==================================================================

# 1. Profil inexistant
d = decide(make_ctx(learning=lci(status="not_started")))
check(
    "S1: not_started → explain (≠ erreur §19)",
    d.action == "explain",
    d.action,
)
check(
    "S1b: not_started n'invente pas de progression (metadata)",
    d.metadata.get("learning_status") == "not_started",
)

# 2. Mastery faible
d = decide(make_ctx(learning=lci(mastery=0.25, confidence=0.8, attempts=3)))
check(
    "S2: mastery weak → review",
    d.action == "review",
    d.action,
)
check(
    "S2b: review recommande create_exercise",
    d.recommended_tool == "create_exercise",
    str(d.recommended_tool),
)

# 3. Mastery intermédiaire
d = decide(make_ctx(learning=lci(mastery=0.50, confidence=0.8, attempts=3)))
check(
    "S3: mastery developing → practice",
    d.action == "practice",
    d.action,
)

# 4. Mastery élevée + confiance élevée
d = decide(make_ctx(learning=lci(mastery=0.92, confidence=0.85, attempts=6)))
check(
    "S4: strong + confidence haute + attempts ok → advance_topic",
    d.action == "advance_topic",
    d.action,
)

# 5. Mastery élevée + confiance basse (§13)
d = decide(make_ctx(learning=lci(mastery=0.78, confidence=0.24, attempts=1)))
check(
    "S5: proficient + confidence 0.24 → evaluate (PAS advance §13)",
    d.action == "evaluate",
    d.action,
)
check(
    "S5b: évaluation recommande assess_understanding",
    d.recommended_tool == "assess_understanding",
)

# 5b. Mastery élevée + confiance basse + déjà tenté → deepen est
# refusé au profit de la confirmation par quiz ? Non §13 : la
# confiance reste basse → evaluate (confirmation systématique).
d = decide(make_ctx(learning=lci(mastery=0.92, confidence=0.20, attempts=4)))
check(
    "S5c: strong + confidence basse → PAS advance_topic",
    d.action != "advance_topic",
    d.action,
)

# 6. Weak point récent (§14)
d = decide(
    make_ctx(
        learning=lci(
            mastery=0.55,
            confidence=0.8,
            attempts=3,
            weak_points=["return vs print"],
        )
    )
)
check(
    "S6: weak point récent + developing → practice ciblé",
    d.action == "practice",
    d.action,
)
check(
    "S6b: la raison cite le weak point",
    "return vs print" in d.reason,
    d.reason,
)

# 7. Régression (§11) — mastery élevée MAIS trend descendant
d = decide(
    make_ctx(
        learning=lci(mastery=0.72, confidence=0.8, attempts=8),
        # pas d'historique réel : on teste via profil semé plus bas
    )
)
# (trajectoire réelle testée avec profil semé en §B)

# 8. Goal prioritaire (§15)
goal_subject = "user-" + uuid.uuid4().hex[:8]
obs = LearningObservation(
    subject="python", topic="functions", type="exercise",
    score=0.92, confidence=1.0,
)
for _ in range(4):
    update_profile_from_observation(goal_subject, obs)
create_learning_goal(
    goal_subject, "python", "Maîtriser les boucles",
    topic="loops",
)
from app.learning.learning_context import (  # noqa: E402
    get_learning_context,
)
lg = get_learning_context(
    user_id=goal_subject, subject="python",
    topic="functions", thread_id="t",
)
d = decide(make_ctx(learning=lg))
check(
    "S8: goal actif sur topic suivant → advance_topic vers le goal",
    d.action == "advance_topic" and d.topic == "loops",
    f"{d.action}/{d.topic}",
)
check(
    "S8b: le goal oriente, la décision documente goal_id",
    d.metadata.get("goal_id") is not None,
)

# 9. Activity en cours (§8/§33)
d = decide(make_ctx(activity=act()))
check(
    "S9: waiting_for_answer → evaluate (jamais nouveau topic)",
    d.action == "evaluate",
    d.action,
)
d = decide(make_ctx(activity=act(status="checking_understanding")))
check(
    "S9b: checking_understanding → continue_activity",
    d.action == "continue_activity",
    d.action,
)
check(
    "S9c: l'activité courante porte activity_id",
    d.activity_id == "a1"
    or d.metadata.get("activity_status") == "checking_understanding",
)

# 10. Topic ambigu (§18)
d = decide(
    make_ctx(
        routing=RoutingResult(
            status="ambiguous", candidates=["python", "sql"]
        )
    )
)
check(
    "S10: ambiguous → clarify (pas de choix arbitraire)",
    d.action == "clarify",
    d.action,
)
check(
    "S10b: candidates transmises dans metadata",
    d.metadata.get("candidates") == ["python", "sql"],
)

# 11. Knowledge absent (§16)
d = decide(
    make_ctx(
        knowledge=K_EMPTY,
        learning=lci(mastery=0.5, confidence=0.8),
    )
)
check(
    "S11: knowledge unavailable → answer (n'invente pas d'exercice)",
    d.action == "answer",
    d.action,
)

# 12. Transitions §34 compatibles Activity State V5.2
check(
    "S12: transitions — idle ouvre les stratégies neuves",
    "practice" in ACTIVITY_TRANSITIONS["idle"]
    and "advance_topic" in ACTIVITY_TRANSITIONS["idle"],
)
check(
    "S12b: waiting_for_answer interdit advance_topic",
    "advance_topic" not in ACTIVITY_TRANSITIONS["waiting_for_answer"],
)
check(
    "S12c: completed ré-ouvre les stratégies",
    "practice" in ACTIVITY_TRANSITIONS["completed"],
)

# 13/14. Isolation A/B + cross-thread (§42)
user_a = "iso-a-" + uuid.uuid4().hex[:6]
user_b = "iso-b-" + uuid.uuid4().hex[:6]
update_profile_from_observation(
    user_a,
    LearningObservation(
        subject="python", topic="functions", type="exercise",
        score=0.30, confidence=1.0,
    ),
)
# B : profil différent (mastery haute)
for _ in range(5):
    update_profile_from_observation(
        user_b,
        LearningObservation(
            subject="python", topic="functions", type="assessment",
            score=0.95, confidence=1.0,
        ),
    )
la = get_learning_context(user_id=user_a, subject="python", topic="functions", thread_id="t")
lb = get_learning_context(user_id=user_b, subject="python", topic="functions", thread_id="t")
da = decide(make_ctx(learning=la), user_id=user_a)
db = decide(make_ctx(learning=lb), user_id=user_b)
check(
    "S13: isolation A≠B — mastery 0.30 vs 0.95 → décisions distinctes",
    da.action != db.action,
    f"{da.action} vs {db.action}",
)
# Cross-thread : même profil, activités différentes (thread-local §50)
bc_same_t1 = make_ctx(learning=lb, activity=act())
bc_same_t2 = make_ctx(learning=lb)
d_t1 = decide(bc_same_t1, user_id=user_b)
d_t2 = decide(bc_same_t2, user_id=user_b)
check(
    "S14: cross-thread — même profil, activité différente → "
    "l'activité prime sur le profil",
    d_t1.action == "evaluate" and d_t2.action != "evaluate",
    f"{d_t1.action} vs {d_t2.action}",
)

# ==================================================================
print("\n--- §11 réel : trajectoire depuis l'historique ---")
# ==================================================================
user_traj = "traj-" + uuid.uuid4().hex[:8]
# Progression réelle : 0.30 → 0.45 → 0.62
for s in (0.30, 0.45, 0.62):
    update_profile_from_observation(
        user_traj,
        LearningObservation(
            subject="python", topic="functions", type="exercise",
            score=s, confidence=1.0,
        ),
    )
lt = get_learning_context(user_id=user_traj, subject="python", topic="functions", thread_id="t")
d_prog = decide(make_ctx(learning=lt), user_id=user_traj)
# mastery après EMA ≈ 0.5x → developing → practice (la progression
# ne court-circuite PAS la zone : on consolide §43)
check(
    "TR1: progression + zone developing → practice (consolider)",
    d_prog.action == "practice",
    f"{d_prog.action} mastery={lt.mastery}",
)

# Régression réelle : haut puis chute répétée
user_reg = "reg-" + uuid.uuid4().hex[:8]
for s in (0.90, 0.70, 0.50, 0.30):
    update_profile_from_observation(
        user_reg,
        LearningObservation(
            subject="python", topic="functions", type="exercise",
            score=s, confidence=1.0,
        ),
    )
lr = get_learning_context(user_id=user_reg, subject="python", topic="functions", thread_id="t")
d_reg = decide(make_ctx(learning=lr), user_id=user_reg)
check(
    "TR2: régression → review (consolider avant d'avancer)",
    d_reg.action in ("review", "practice"),
    d_reg.action,
)

# ==================================================================
print("\n--- §43 : conflits de règles ---")
# ==================================================================

# Conflit 1 : mastery faible + goal actif + activité en cours
# Priorité attendue (§8) : ACTIVITÉ > besoin > goal > nouveau topic
d = decide(
    make_ctx(
        learning=lci(mastery=0.25, confidence=0.8, attempts=1),
        activity=act(),
    )
)
check(
    "C1: activité > mastery faible > goal → evaluate (l'activité prime)",
    d.action == "evaluate",
    d.action,
)

# Conflit 2 : mastery élevée + weak point récent
# Priorité attendue : le weak point (W=5) passe devant advance
d = decide(
    make_ctx(
        learning=lci(
            mastery=0.88, confidence=0.85, attempts=5,
            weak_points=["récursion récursive"],
        )
    )
)
check(
    "C2: strong + weak point → practice ciblé (weak point > advance)",
    d.action == "practice",
    d.action,
)

# Conflit 3 : ambiguous + activité en cours
# L'activité courante prime même sur la clarification
d = decide(
    make_ctx(
        routing=RoutingResult(status="ambiguous", candidates=["a", "b"]),
        activity=act(),
    )
)
check(
    "C3: ambiguous + activité en cours → l'activité prime",
    d.action in ("evaluate", "continue_activity"),
    d.action,
)

# ==================================================================
print("\n--- §44 : stabilité déterministe ---")
# ==================================================================

bc_stable = make_ctx(
    learning=lci(mastery=0.55, confidence=0.6, attempts=4,
                 weak_points=["boucles while"])
)
first = decide(bc_stable).model_dump()
stable = all(
    decide(bc_stable).model_dump() == first for _ in range(5)
)
check(
    "ST1: même BuiltContext → même décision (5 exécutions)",
    stable,
)
import pydantic  # noqa: E402
try:
    LearningDecision(action="answer", reason="r", score_interne=1)
    ok_forbid = False
except pydantic.ValidationError:
    ok_forbid = True
check(
    "ST2: LearningDecision(score_interne=...) REJETÉ (extra=forbid)",
    ok_forbid,
)

# ==================================================================
print("\n--- §4.1/§17/§18 : garde-fous code source ---")
# ==================================================================

import inspect  # noqa: E402
from app.learning import engine as _engine_mod  # noqa: E402

src = inspect.getsource(_engine_mod)
check(
    "G1: engine n'appelle PAS write/update profile (§4.1)",
    "write_learning_profile" not in src
    and "update_profile_from_observation(" not in src,
)
check(
    "G2: engine ne recrée PAS router/recherche (§17/§18)",
    "route_subject(" not in src
    and "web_search(" not in src
    and "search_knowledge(" not in src,
)
check(
    "G3: engine consomme BuiltContext (§26 signature decide(context))",
    "context: BuiltContext" in src,
)

# ==================================================================
# §45 : INTÉGRATION LLM RÉELLE — nécessite le serveur BASE_PORT.
# ==================================================================
port = os.environ.get("BASE_PORT", "8001")
base = f"http://127.0.0.1:{port}"

if os.environ.get("SKIP_LLM_TESTS") == "1":
    print("\n(§45 intégré LLM sauté — SKIP_LLM_TESTS=1)")
else:
    import json  # noqa: E402
    import urllib.request  # noqa: E402

    def api(path, method="GET", payload=None, token=None):
        # Mission Identité : session simulée ( mode dev ) — le
        # user_id du path/body est TOUJOURS le sien ( pas d'autre
        # user dans cette suite ).
        if token is None:
            token = _V7_TOKEN[0]
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(
            base + path,
            method=method,
            data=(
                json.dumps(payload).encode() if payload else None
            ),
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read().decode())

    _V7_TOKEN = [None]

    try:
        api("/api/health")
        server_ok = True
    except Exception:
        server_ok = False

    if not server_ok:
        print("\n(§45 sauté : serveur absent — parties A-C suffisantes)")
    else:
        print("\n--- §45 : intégration LLM réelle ---")

        # Étudiant python, mastery faible semée, question fonctions
        # → le moteur doit décider, le LLM exécuter naturellement.
        _u = api(
            "/api/users", "POST", {"name": "V7-Learning-" + uuid.uuid4().hex[:4]}
        )
        user_id = _u["user_id"]
        _V7_TOKEN[0] = _u.get("dev_token", "dev:" + user_id)
        for s in (0.35, 0.40):
            update_profile_from_observation(
                user_id,
                LearningObservation(
                    subject="python", topic="functions",
                    type="exercise", score=s, confidence=1.0,
                ),
            )
        thread_id = api(
            f"/api/users/{user_id}/threads", "POST",
            {"name": "v7-engine"},
        )["thread_id"]

        chat = api(
            "/api/chat", "POST",
            {
                "user_id": user_id,
                "thread_id": thread_id,
                "message": "Explique-moi les fonctions python",
            },
        )
        check(
            "L1: chat réel répond (agent_response présent)",
            "agent_response" in chat and bool(chat.get("response")),
            str(chat)[:100],
        )

        # Le moteur a-t-il décidé AVANT le LLM ? — logs du serveur
        # (read_log_file : agent.log partagé — le bus in-process du
        # test ne voit PAS les events du serveur).
        from app.logging.events import read_log_file  # noqa: E402

        events = read_log_file(limit=400)
        decisions = [
            e for e in events
            if e.get("event") == "LEARNING_DECISION"
            and e.get("user_id") == user_id
        ]
        check(
            "L2: LEARNING_DECISION loggué pour ce user",
            len(decisions) >= 1,
            f"{len(decisions)} decisions",
        )
        if decisions:
            last = decisions[-1]
            check(
                "L3: la décision porte action/reason/priority "
                "(§46 — pas de messages complets)",
                bool(last.get("action"))
                and bool(last.get("reason"))
                and "priority" in last,
                str(last)[:150],
            )

        # §47 : preview expose la stratégie
        pv = api(
            "/api/context/preview", "POST",
            {
                "user_id": user_id,
                "thread_id": thread_id,
                "query": "comment retourner une valeur",
            },
        )
        check(
            "L4: preview expose learning_strategy (§47 Inspector)",
            pv.get("learning_strategy") is not None
            and bool(pv["learning_strategy"].get("action")),
            str(pv.get("learning_strategy"))[:120],
        )
        check(
            "L5: prompt_preview contient LEARNING STRATEGY (§31)",
            "LEARNING STRATEGY" in pv.get("prompt_preview", ""),
        )
        check(
            "L6: pas de scores internes dans le prompt (§31)",
            "priority" not in pv.get("prompt_preview", "")
            and "W_CURRENT_ACTIVITY" not in pv.get("prompt_preview", ""),
        )

# ==================================================================
print(f"\nTOTAL: {PASS + FAIL} | PASS: {PASS} | FAIL: {FAIL}")
if FAIL:
    print("ÉCHECS LEARNING ENGINE V7")
    sys.exit(1)
print("TESTS V7 LEARNING ENGINE: OK")
