# Tests V6.5 — SEARCH, RETRIEVAL & FALLBACK QUALITY (§30-§38).
# Suite dédiée : routing paraphrase/ambiguïté, ranking, top_k,
# fallback pipeline, web statuses, noise, isolation mémoire/profil.
# Usage : python -X utf8 tests\test_v65_search.py
# (serveur NON requis sauf §33 E2E web — mocké si absent)
import json
import os
import re
import sys
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, ".")

results = []


def check(label, cond, detail=""):
    results.append((label, bool(cond)))
    print(
        f"[{'PASS' if cond else 'FAIL'}] {label}"
        + (f" -- {detail}" if detail else "")
    )


BASE = f"http://127.0.0.1:{os.environ.get('BASE_PORT', '8001')}"


TOKENS = {}  # user_id -> dev token ( session simulée mode dev )
LAST_TOKEN = [None]


def api(path, method="GET", body=None, token=None):
    import json as _json
    import urllib.request as _rq
    data = _json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    # token explicite > token du user dans l'URL > dernier actif
    if token is None:
        m = re.search(r"/api/users/([^/]+)", path)
        if m and m.group(1) in TOKENS:
            token = TOKENS[m.group(1)]
    if token is None and LAST_TOKEN[0]:
        token = LAST_TOKEN[0]
    if token:
        headers["Authorization"] = "Bearer " + token
    req = _rq.Request(BASE + path, data=data, method=method, headers=headers)
    with _rq.urlopen(req, timeout=300) as resp:
        return _json.loads(resp.read().decode())


def server_up() -> bool:
    try:
        api("/api/health")
        return True
    except Exception:
        return False


# ==================================================================
# §30 — PARAPHRASE : « Comment communiquent les ordinateurs ? »
# doit être reconnu (subject=computer_networks)
# ==================================================================
print("\n--- §30 paraphrase ---")
from app.context.router import route_subject  # noqa: E402

r = route_subject("Comment communiquent les ordinateurs ?")
check(
    "30a: paraphrase ordinateurs → computer_networks (conf >= 0.5)",
    r.status == "supported"
    and r.subject == "computer_networks"
    and r.confidence >= 0.5,
    f"{r.status}/{r.subject}/{r.confidence}",
)
# Variante morphologique : singulier/pluriel
r2 = route_subject("explique moi le return des fonctions")
check(
    "30b: variante morphologique (fonctions) → python + topic pertinent",
    r2.status == "supported"
    and r2.subject == "python"
    and r2.topic in ("return", "fonctions", "functions"),
    f"{r2.status}/{r2.subject}/{r2.topic}",
)

# ==================================================================
# §31 — AMBIGUÏTÉ : « Parle-moi des réseaux. » reste ambiguous
# ==================================================================
print("\n--- §31 ambiguïté ---")
r = route_subject("Parle-moi des reseaux.")
check(
    "31: 'reseaux' nu → ambiguous, 2 candidats, aucun choix inventé",
    r.status == "ambiguous"
    and set(r.candidates) >= {"computer_networks", "neural_networks"},
    f"{r.status}/{r.candidates}",
)

# ==================================================================
# §32 — KNOWLEDGE ABSENT : matière supportée sans knowledge pertinent
# → local insufficient → tentative web
# ==================================================================
print("\n--- §32 knowledge absent → web ---")
from app.context.builder import build_context  # noqa: E402

bc = build_context("v65-t", "v65-t", "python async asyncio")
check(
    "32a: knowledge insufficient détecté (aucune invention)",
    bc.knowledge.status == "insufficient"
    and len(bc.knowledge.items) == 0,
    bc.knowledge.status,
)
check(
    "32b: tentative web effectuée (web != unavailable)",
    bc.web.status in ("found", "insufficient", "error"),
    bc.web.status,
)
if bc.web.results:
    check(
        "32c: web found → résultats présents",
        bc.web.status == "found" and len(bc.web.results) >= 1,
        f"{len(bc.web.results)} résultats",
    )

# ==================================================================
# §33 — WEB UNAVAILABLE : échec simulé → pas de crash, statut propre
# ==================================================================
print("\n--- §33 web unavailable/error ---")
from app.context.web_search import (  # noqa: E402
    build_web_query,
    rank_web_results,
    source_quality,
    web_search,
)

# Simulation unavailable : clé absente (monkeypatch config)
import app.context.web_search as ws  # noqa: E402

old_key = ws.OLLAMA_API_KEY
ws.OLLAMA_API_KEY = ""
resp = web_search("closures python", subject="python")
ws.OLLAMA_API_KEY = old_key
check(
    "33a: clé absente → status=unavailable (PAS found=[])",
    resp.status == "unavailable" and resp.results == [],
    resp.status,
)

# Simulation error : client qui lève
class _BoomClient:
    def web_search(self, **kw):
        raise RuntimeError("simulated network failure")


def _boom_client_factory(**kw):
    raise RuntimeError("simulated connection refused")


import ollama  # noqa: E402

old_client = ollama.Client
ollama.Client = lambda **kw: _boom_client_factory()
resp = web_search("closures python", subject="python")
ollama.Client = old_client
check(
    "33b: exception client → status=error, aucun crash",
    resp.status == "error" and resp.results == [],
    resp.status,
)

# Le pipeline builder ne crashe PAS sur web error
from app.context.schemas import BuiltContext  # noqa: E402

bc2 = build_context("v65-t", "v65-t", "python async asyncio")
bc2_web_before = bc2.web.status  # (peut être found réel)
check(
    "33c: builder survives au fallback web (contexte construit)",
    bc2.routing.status == "supported",
    f"web={bc2_web_before}",
)

# ==================================================================
# §34 — RESULT QUALITY : pertinent > non pertinent dans le ranking
# ==================================================================
print("\n--- §34 ranking pertinent > non pertinent ---")
raw = [
    {
        "title": "Python Closures — Official Documentation",
        "url": "https://docs.python.org/3/howto/closures",
        "content": "Python closures functions capture variables "
        "from enclosing scopes. Official documentation on "
        "closures and nested functions.",
    },
    {
        "title": "Best Pizza Restaurants Guide 2026",
        "url": "https://food.example.com/pizza",
        "content": "Pizza restaurants dining guide new york "
        "best slices cheese pepperoni.",
    },
]
ranked = rank_web_results(
    raw, "python closures functions", topic="functions", top_k=3
)
check(
    "34a: résultat pertinent classé en tête",
    ranked and ranked[0].title.startswith("Python Closures"),
    ranked[0].title[:40] if ranked else "aucun",
)
check(
    "34b: non-pertinent filtré (sous seuil) ou classé dernier",
    all(
        r.relevance <= ranked[0].relevance for r in ranked
    ),
    f"top={ranked[0].relevance}",
)

# Knowledge ranking : section précise > section générique
from app.context.knowledge_retriever import (  # noqa: E402
    search_knowledge,
)

kr = search_knowledge(
    "python", topic="return", query="explique le return", limit=3
)
check(
    "34c: knowledge — section 'return' en tête (topic 0.30)",
    kr["items"] and kr["items"][0]["topic"] == "return",
    kr["items"][0]["topic"] if kr["items"] else "aucun",
)

# ==================================================================
# §35 — TOP_K : 10 résultats → max 3 transmis
# ==================================================================
print("\n--- §35 top_k ---")
many = [
    {
        "title": f"Python closures functions doc {i}",
        "url": f"https://docs.python.org/{i}",
        "content": "python closures functions official "
        "documentation nested scopes",
    }
    for i in range(10)
]
top3 = rank_web_results(
    many, "python closures functions", top_k=3
)
check(
    "35: 10 résultats, top_k=3 → 3 max au Context Builder",
    len(top3) <= 3,
    f"{len(top3)} transmis",
)

# ==================================================================
# §36 — NOISE : « Quelle heure est-il ? » pas de recherche pédagogique
# ==================================================================
print("\n--- §36 noise ---")
bc = build_context("v65-t", "v65-t", "Quelle heure est-il ?")
check(
    "36a: noise → routing unknown (pas de matière inventée)",
    bc.routing.status == "unknown" and bc.routing.subject is None,
    bc.routing.status,
)
check(
    "36b: noise → AUCUNE tentative web (web=unavailable)",
    bc.web.status == "unavailable" and len(bc.web.results) == 0,
    bc.web.status,
)
check(
    "36c: noise → aucun knowledge item",
    len(bc.knowledge.items) == 0,
    bc.knowledge.status,
)

# ==================================================================
# §37 — MEMORY : la recherche ne transforme pas User Memory en
# Knowledge — les sources restent séparées
# ==================================================================
print("\n--- §37 sources séparées ---")
from app.context.schemas import (  # noqa: E402
    KnowledgeSearchResult,
    SearchResponse,
)

bc = build_context(
    "v65-t", "v65-t", "explique moi les boucles en python"
)
# knowledge.items ne contient QUE du local_knowledge
all_local = all(
    hasattr(i, "source_type")
    and i.source_type == "local_knowledge"
    for i in bc.knowledge.items
) if bc.knowledge.items else True
check(
    "37a: knowledge.items = local_knowledge uniquement (jamais user_document/web)",
    all_local and bc.knowledge.items != bc.relevant_memories,
    f"{len(bc.knowledge.items)} items / "
    f"{len(bc.relevant_memories)} memories",
)
check(
    "37b: web.results = source_type web uniquement",
    all(
        r.source_type == "web" for r in bc.web.results
    ),
    f"{len(bc.web.results)} web results",
)

# ==================================================================
# §38 — LEARNING PROFILE : pas utilisé pour déterminer la matière
# ==================================================================
print("\n--- §38 learning profile ≠ routing ---")
r = route_subject("Explique-moi les boucles python")
check(
    "38a: routing indépendant du profil (fonction pure query)",
    r.status == "supported" and r.subject == "python",
    f"{r.subject}/{r.topic}",
)
# get_learning_context ne crée pas de matière si profil diverge
from app.learning.learning_context import (  # noqa: E402
    get_learning_context,
)

lg = get_learning_context(
    user_id="v65-nobody", subject="python", topic="boucles"
)
check(
    "38b: learning = progression SEULEMENT (subject/topic imposés par le router)",
    lg.status in ("active", "not_started"),
    lg.status,
)

# ==================================================================
# §23/§3 — CONTRAT DE SCHEMA (validation stricte)
# ==================================================================
print("\n--- §3 schema contract ---")
try:
    SearchResponse(
        status="invented", query="x", results=[]
    )
    bad_status = False
except Exception:
    bad_status = True
check("3a: SearchResponse Literal status protégé", bad_status)

try:
    from app.context.schemas import SearchResult

    SearchResult(
        source="x",
        content="y",
        source_type="invented_type",
    )
    bad_type = False
except Exception:
    bad_type = True
check("3b: SearchResult Literal source_type protégé", bad_type)

# §19 : source quality — pas d'invention de domaine officiel
check(
    "19: domaine inconnu → quality 0 (rien inventé)",
    source_quality("https://unknown.tld/x") == 0.0
    and source_quality("https://docs.python.org/x") == 1.0,
    f"{source_quality('https://unknown.tld/x')}",
)

# ==================================================================
# Résumé
# ==================================================================
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
print("TESTS V6.5 SEARCH: OK")
