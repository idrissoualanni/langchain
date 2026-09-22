# Tests V6.7 — STRUCTURED AGENT OUTPUT (§34 + ADDENDUM §13).
import sys
import warnings

sys.path.insert(0, ".")
warnings.filterwarnings("ignore")

results = []


def check(label, cond, detail=""):
    results.append((label, bool(cond)))
    print(
        f"[{'PASS' if cond else 'FAIL'}] {label}"
        + (f" -- {detail}" if detail else "")
    )


from app.services.agent.normalizer import (  # noqa: E402
    normalize_response,
    response_from_activity,
    response_from_clarification,
    response_from_error,
    response_from_search,
    response_from_text,
)
from app.schemas.response import AgentResponse  # noqa: E402
from app.services.context.fallback import decide_fallback  # noqa: E402
from app.schemas.context import FallbackDecision  # noqa: E402

print("--- §19 : les 9 types convertibles ---")

TYPES = [
    ("text", "explication"),
    ("exercise", "exercice"),
    ("quiz", "quiz"),
    ("evaluation", "évaluation"),
    ("hint", "indice"),
    ("code", "code"),
    ("search", "recherche"),
    ("clarification", "clarification"),
    ("error", "erreur"),
]
for t, _ in TYPES:
    r = AgentResponse(type=t, status="completed", message="m")
    check(
        f"type « {t} » valide et convertible",
        r.type == t and r.version == 1,
    )

print("--- ADDENDUM §13 : les 5 statuts publics + success refusé ---")
for s in ("completed", "waiting_for_user", "running",
          "error", "cancelled"):
    r = AgentResponse(type="text", status=s, message="m")
    check(f"statut « {s} » accepté", r.status == s)

try:
    AgentResponse(type="text", status="success", message="m")
    ok = False
except Exception:
    ok = True
check("statut « success » REFUSÉ (ADDENDUM §7)", ok)

try:
    AgentResponse(type="invented", status="completed", message="m")
    ok = False
except Exception:
    ok = True
check("type inventé refusé (Literal protégé)", ok)

print("--- ADDENDUM §8 : activity.status ≠ AgentResponse.status ---")
# checking_understanding (activité) → evaluation/waiting_for_user
r = response_from_activity(
    "explique",
    {"activity_type": "exercise",
     "status": "checking_understanding", "activity_id": "x"},
)
check(
    "checking_understanding → evaluation/waiting_for_user "
    "(backend vérifie, frontend attend)",
    r.type == "evaluation" and r.status == "waiting_for_user",
    f"{r.type}/{r.status}",
)
# completed (activité) → evaluation/completed
r = response_from_activity(
    "bravo",
    {"activity_type": "exercise", "status": "completed",
     "activity_id": "x"},
)
check(
    "activity completed → evaluation/completed",
    r.type == "evaluation" and r.status == "completed",
)
# abandoned → cancelled (≠ error)
r = response_from_activity(
    "ok",
    {"activity_type": "exercise", "status": "abandoned",
     "activity_id": "x"},
)
check(
    "activity abandoned → cancelled (≠ error)",
    r.status == "cancelled",
)

print("--- §20-§22 : data par type ---")
r = response_from_activity(
    "Voici ton exercice.",
    {
        "activity_type": "exercise",
        "status": "waiting_for_answer",
        "activity_id": "act_123",
        "subject": "python",
        "topic": "return",
    },
)
check(
    "§20 exercise data (activity_id/subject/topic) + actions",
    r.data.get("activity_id") == "act_123"
    and r.data.get("subject") == "python"
    and {"type": "submit_answer"} in r.actions
    and {"type": "request_hint"} in r.actions,
    str(r.actions),
)
r = response_from_activity(
    "Q1",
    {
        "activity_type": "quiz",
        "status": "waiting_for_answer",
        "activity_id": "q1",
        "question_index": 2,
        "total_questions": 5,
    },
)
check(
    "§21 quiz : UNE question à la fois (index/total)",
    r.data.get("question_index") == 2
    and r.data.get("total_questions") == 5,
    f"{r.data.get('question_index')}/{r.data.get('total_questions')}",
)
r = response_from_activity(
    "Code",
    {
        "activity_type": "code",
        "status": "waiting_for_answer",
        "activity_id": "c1",
        "language": "python",
        "starter_code": "def f():\n    pass",
    },
)
check(
    "§22 code : language + starter_code (frontend → CodeEditor)",
    r.data.get("language") == "python"
    and "def f()" in r.data.get("starter_code", ""),
)

print("--- §23 : jamais exposer keyword list / hidden answer ---")
r = response_from_search(
    "sources",
    [
        {
            "title": "t",
            "source": "docs.python.org",
            "url": "https://x",
            "snippet": "s",
            "expected_answer": "SECRET",
            "hidden_answer": "SECRET2",
            "keywords": ["k1"],
            "scoring": {"internal": 1},
        }
    ],
)
flat = str(r.model_dump())
leaks = [
    k
    for k in ("expected_answer", "hidden_answer",
              "keywords", "scoring")
    if k in flat
]
check("§23 search : aucune clé interne fuiter", not leaks,
      str(leaks))

print("--- §24 : search réutilise SearchResult (pas de 2e système) ---")
from app.schemas.context import SearchResult  # noqa: E402

sr = SearchResult(
    title="Docs", source="docs.python.org",
    url="https://docs.python.org/x", content="c" * 400,
    snippet="snip", relevance=0.9, source_type="web",
)
r = response_from_search("m", [sr.model_dump()])
check(
    "§24 SearchResponse → AgentResponse.search (title/source/url/snippet)",
    r.type == "search"
    and r.data["results"][0]["url"] == "https://docs.python.org/x"
    and "relevance" not in r.data["results"][0],
)

print("--- §25 : clarification avec boutons ---")
r = response_from_clarification(
    "Réseaux info ou neuronaux ?",
    candidates=["computer_networks", "neural_networks"],
)
check(
    "§25 select options + waiting_for_user",
    r.actions
    and r.actions[0]["type"] == "select"
    and r.actions[0]["options"] == [
        "computer_networks", "neural_networks"
    ]
    and r.status == "waiting_for_user",
)

print("--- §5 ADDENDUM : error propre (jamais stack trace) ---")
r = response_from_error("La recherche n'est pas disponible.")
check(
    "error sans traceback/chemin/secret",
    r.status == "error"
    and "Traceback" not in r.message
    and "C:\\" not in r.message,
)

print("--- ADDENDUM §9 : couches indépendantes ---")
d = decide_fallback(
    "supported", knowledge_status="insufficient",
    web_status="found", has_web_results=True,
)
r = normalize_response("Le voici.", fallback=d)
check(
    "SearchResponse.insufficient → FallbackDecision.use_web_search"
    " → AgentResponse completed (chacun son vocabulaire)",
    d.action == "use_web_search"
    and r.type == "text"
    and r.status == "completed",
    f"{d.action} → {r.type}/{r.status}",
)

# normalize_response avec search réel
r = normalize_response(
    "Réponse web", search_results=[sr.model_dump()],
    search_used=True,
)
check(
    "normalize_response routing search quand search_used",
    r.type == "search" and r.status == "completed",
)

# fallback clarification via normalize_response
d = decide_fallback("ambiguous")
d.candidates = ["a", "b"]
r = normalize_response("Précise", fallback=d)
check(
    "normalize_response : fallback ambiguous → clarification",
    r.type == "clarification"
    and r.actions[0]["options"] == ["a", "b"],
)

print("--- §26 : le normalizer ne dépend pas du LLM ---")
r = normalize_response("texte seul")
check(
    "texte seul → text/completed sans activité",
    r.type == "text" and r.status == "completed",
)

# Résumé
print()
fails = [label for label, ok in results if not ok]
print(
    f"TOTAL: {len(results)} | PASS: {len(results) - len(fails)} "
    f"| FAIL: {len(fails)}"
)
if fails:
    print("ECHECS:")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("TESTS V6.7 OUTPUT: OK")
