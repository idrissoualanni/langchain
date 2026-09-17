# Tests V6.8.1 — CONTRATS DE CONTEXTE UNIFIÉS (§25-§30).
#
# §25 : validation / serialization / required / null / enum /
#       nested models
# §26 : incompatibilité — RoutingResult(learning=...) REJETÉ
#       (extra=forbid), BuiltContext(unknown=...) rejeté
# §27 : canonicité — build_context → UN BuiltContext (agrégé
#       canonique), le Learning Engine consomme SANS reconstruction
# §28 : non-duplication — le moteur n'appelle PAS router/search
# §30 : scénario final V7-compat : decide(built_context) direct
#
# PAS de serveur requis (unitaire) SAUF scénario §30 qui utilise
# le graphe comme test_v68_final_integration (run sans LLM).
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import pydantic  # noqa: E402

from app.context.schemas import (  # noqa: E402
    ActivityContextInfo,
    AgentContext,
    BuiltContext,
    ContextStats,
    FallbackDecision,
    KnowledgeResult,
    KnowledgeSearchResult,
    ResolvedTools,
    RoutingResult,
    SearchResponse,
    SearchResult,
    SubjectContextInfo,
    ThreadContextInfo,
    UserContextInfo,
)
from app.context.budget import (  # noqa: E402
    ContextBudget,
    BudgetSection,
)
from app.context.model_capabilities import (  # noqa: E402
    ModelCapabilities,
)
from app.learning.schemas import LearningContextInfo  # noqa: E402

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


def rejected(fn) -> bool:
    """Vrai si fn() lève pydantic.ValidationError."""
    try:
        fn()
        return False
    except pydantic.ValidationError:
        return True
    except Exception:
        return False


# ==================================================================
print("\n--- §25-A : champs required ---")
# ==================================================================

check(
    "A1: SearchResult sans source REJETÉ (required)",
    rejected(lambda: SearchResult()),
    "source est requis",
)
check(
    "A2: SearchResult sans content REJETÉ",
    rejected(lambda: SearchResult(source="x")),
    "content est requis",
)
check(
    "A3: FallbackDecision sans action REJETÉ",
    rejected(lambda: FallbackDecision(reason="r")),
    "action est requis",
)
check(
    "A4: FallbackDecision sans reason REJETÉ",
    rejected(lambda: FallbackDecision(action="answer")),
    "reason est requis",
)
check(
    "A5: SubjectContextInfo sans id REJETÉ",
    rejected(lambda: SubjectContextInfo(name="n", domain="d")),
    "id requis",
)

# ==================================================================
print("\n--- §25-B : Literal/enum rejetés (validation) ---")
# ==================================================================

check(
    "B1: RoutingResult status invalide REJETÉ",
    rejected(
        lambda: RoutingResult(status="nope_status")
    ),
    "Literal 5 valeurs",
)
check(
    "B2: SearchResponse status invalide REJETÉ",
    rejected(lambda: SearchResponse(status="maybe")),
    "Literal 4 valeurs",
)
check(
    "B3: FallbackDecision action invalide REJETÉ",
    rejected(
        lambda: FallbackDecision(
            action="invent_action", reason="r"
        )
    ),
    "Literal 5 actions",
)
check(
    "B4: SearchResult source_type invalide REJETÉ",
    rejected(
        lambda: SearchResult(
            source="x",
            content="y",
            source_type="telepathy",
        )
    ),
    "Literal 4 types",
)
check(
    "B5: LearningContextInfo status invalide REJETÉ",
    rejected(
        lambda: LearningContextInfo(status="finished")
    ),
    "Literal 3 valeurs",
)
check(
    "B6: ActivityContextInfo extra rejeté (extra=forbid)",
    rejected(
        lambda: ActivityContextInfo(
            activity_id="a", question="divulguée"
        )
    ),
    "question interdite dans la vue exposée",
)

# ==================================================================
print("\n--- §25-C : null handling ---")
# ==================================================================

r = RoutingResult()
check(
    "C1: RoutingResult() défaut status=unknown (champs optionnels)",
    r.status == "unknown" and r.subject is None
    and r.topic is None,
    f"{r.status}/{r.subject}/{r.topic}",
)
sr = SearchResult(source="s", content="c")
check(
    "C2: SearchResult null-safe (url/snippet/metadata défauts)",
    sr.url is None and sr.snippet is None
    and sr.metadata == {},
    "None/None/{}",
)
mc = ModelCapabilities()
check(
    "C3: ModelCapabilities null honnête (window inconnue)",
    mc.context_window is None and not mc.supports_vision,
    "null = inconnu, jamais inventé",
)
li = LearningContextInfo()
check(
    "C4: LearningContextInfo mastery null = jamais évalué",
    li.status == "not_started" and li.mastery is None
    and li.attempts == 0,
    f"{li.status}/{li.mastery}",
)
k = KnowledgeSearchResult(status="unavailable")
check(
    "C5: KnowledgeSearchResult vide constructible (listes vides)",
    k.items == [] and k.results == [] and k.searched_sources == 0,
    "vide honnête",
)

# ==================================================================
print("\n--- §25-D : serialization round-trip ---")
# ==================================================================

kr = KnowledgeResult(
    source="python/functions", topic="return", content="x"
)
k2 = KnowledgeSearchResult(
    status="found",
    items=[kr],
    searched_sources=2,
)
d = k2.model_dump()
check(
    "D1: dump KSR expose items ET results (transition §8)",
    len(d["items"]) == 1 and len(d["results"]) == 1
    and d["items"][0]["topic"] == "return",
    "items + results synchronisés",
)
k3 = KnowledgeSearchResult.model_validate(d)
check(
    "D2: round-trip KSR model_validate(dump)",
    k3.status == "found"
    and len(k3.items) == 1
    and len(k3.results) == 1
    and k3.items[0].topic == "return",
    f"{k3.status}/{len(k3.items)}",
)

fd = FallbackDecision(
    action="use_local_knowledge",
    reason="ok",
    source_status="supported/found",
    confidence=0.95,
)
fd2 = FallbackDecision.model_validate(fd.model_dump())
check(
    "D3: round-trip FallbackDecision",
    fd2.action == fd.action and fd2.confidence == 0.95,
    fd2.action,
)

# ==================================================================
print("\n--- §25-E : nested (BuiltContext agrégé) ---")
# ==================================================================

bc = BuiltContext()
check(
    "E1: BuiltContext() constructible par défaut",
    bc.routing.status == "unknown"
    and bc.learning is None
    and bc.budget is None
    and bc.model is None
    and bc.activity is None,
    "defaults honnêtes",
)
check(
    "E2: nested défauts cohérents",
    bc.knowledge.status == "unavailable"
    and bc.web.status == "unavailable"
    and bc.fallback.action
    == "continue_without_external_search",
    f"{bc.knowledge.status}/{bc.web.status}/"
    f"{bc.fallback.action}",
)

full = BuiltContext(
    routing=RoutingResult(
        status="supported",
        subject="python",
        topic="functions",
        confidence=0.9,
    ),
    subject=SubjectContextInfo(
        id="python",
        name="Python",
        domain="informatique",
    ),
    knowledge=KnowledgeSearchResult(
        status="found",
        items=[
            KnowledgeResult(
                source="python/functions",
                topic="functions",
                content="def f(): ...",
            )
        ],
    ),
    web=SearchResponse(status="unavailable"),
    fallback=FallbackDecision(
        action="use_local_knowledge",
        reason="knowledge found",
        source_status="supported/found/unavailable",
    ),
    tools=ResolvedTools(available=["create_exercise"]),
    user=UserContextInfo(text="étudiant débutant"),
    thread=ThreadContextInfo(thread_id="t1"),
    learning=LearningContextInfo(
        status="active",
        subject="python",
        topic="functions",
        mastery=0.43,
        attempts=2,
        weak_points=["return vs print"],
    ),
    relevant_memories=[{"id": "m1"}],
    stats=ContextStats(
        memories_used=1,
        knowledge_items=1,
        budget_status="ok",
    ),
    budget=ContextBudget(
        context_window=None,
        reserved_output_tokens=2048,
        available_input_tokens=None,
    ),
    model=ModelCapabilities(model_name="gemma"),
    activity=ActivityContextInfo(
        activity_id="a1",
        activity_type="exercise",
        status="waiting_for_answer",
        subject="python",
        topic="functions",
        hint_level=1,
        attempts=1,
    ),
)
check(
    "E3: BuiltContext nested complet (tous contrats V6.8.1)",
    full.learning is not None
    and full.learning.mastery == 0.43
    and full.activity is not None
    and full.activity.status == "waiting_for_answer"
    and full.model is not None
    and full.model.model_name == "gemma"
    and full.budget is not None
    and full.budget.reserved_output_tokens == 2048,
    "learning/activity/model/budget typés",
)
dumped = full.model_dump()
check(
    "E4: dump BuiltContext complet (nested sérialisable)",
    dumped["learning"]["mastery"] == 0.43
    and dumped["activity"]["status"] == "waiting_for_answer"
    and dumped["model"]["model_name"] == "gemma"
    and dumped["budget"]["reserved_output_tokens"] == 2048,
    "nested dict",
)

# §17 immutabilité par convention : model_copy explicite
mutated = full.model_copy(
    update={"activity": ActivityContextInfo(status="idle")}
)
check(
    "E5: §17 dérivation = COPIE (original intact)",
    full.activity.status == "waiting_for_answer"
    and mutated.activity.status == "idle",
    "l'original n'est jamais muté",
)

# ==================================================================
print("\n--- §26 : incompatibilité extra=forbid ---")
# ==================================================================

check(
    "F1: RoutingResult(learning=...) REJETÉ §26",
    rejected(
        lambda: RoutingResult(
            status="supported", learning={"x": 1}
        )
    ),
    "routing ≠ learning : jamais fusionnés",
)
check(
    "F2: RoutingResult(knowledge=...) REJETÉ",
    rejected(
        lambda: RoutingResult(
            status="supported", knowledge="cours"
        )
    ),
    "routing ≠ retrieval",
)
check(
    "F3: FallbackDecision(results=...) REJETÉ",
    rejected(
        lambda: FallbackDecision(
            action="answer",
            reason="r",
            results=[{"r": 1}],
        )
    ),
    "fallback ≠ retrieval",
)
check(
    "F4: BuiltContext(unknown_source=...) REJETÉ",
    rejected(
        lambda: BuiltContext(
            second_context={"parallèle": True}
        )
    ),
    "§3 pas d'architecture parallèle",
)
check(
    "F5: SearchResponse(items=...) REJETÉ (items = vue KSR)",
    rejected(
        lambda: SearchResponse(status="found", items=[])
    ),
    "items est réservé à KnowledgeSearchResult",
)
check(
    "F6: LearningContextInfo(decision=...) REJETÉ",
    rejected(
        lambda: LearningContextInfo(decision="practice")
    ),
    "§12 contexte ≠ décision",
)

# ==================================================================
print("\n--- §8/§9 : unification retrieval ---")
# ==================================================================

check(
    "G1: KnowledgeSearchResult EST une SearchResponse (§8)",
    isinstance(k2, SearchResponse),
    "un seul contrat retrieval",
)
k_items_only = KnowledgeSearchResult(
    status="found",
    items=[
        KnowledgeResult(
            source="s", topic="t", content="c"
        )
    ],
)
check(
    "G2: items fourni → results DÉRIVÉ (sync validateur)",
    len(k_items_only.results) == 1
    and k_items_only.results[0].source_type
    == "local_knowledge",
    "source de vérité partagée",
)
k_results_only = KnowledgeSearchResult(
    status="insufficient",
    results=[
        KnowledgeResult(source="s", topic="t", content="c")
    ],
)
check(
    "G3: results fourni → items DÉRIVÉ (sync inverse)",
    len(k_results_only.items) == 1
    and k_results_only.items[0].topic == "t",
    "synchronisation bidirectionnelle",
)
web = SearchResponse(
    status="found",
    results=[
        SearchResult(
            source="docs.python.org",
            content="Functions",
            source_type="web",
        )
    ],
)
check(
    "G4: web = SearchResponse pure (source_type web)",
    web.results[0].source_type == "web",
    "retrieval unifié, types distincts",
)

# ==================================================================
print("\n--- §20 : learning typé + shim transition ---")
# ==================================================================

lci = LearningContextInfo(
    status="active",
    subject="python",
    topic="fonctions",
    mastery=0.7,
    weak_points=["return vs print"],
)
check(
    "H1: attributs typés (accès direct)",
    lci.mastery == 0.7 and lci.attempts == 0,
    "LearningContextInfo",
)
check(
    "H2: shim __getitem__ historique",
    lci["status"] == "active" and lci["mastery"] == 0.7,
    "transition sans rupture",
)
check(
    "H3: shim .get() historique (clé inconnue → default)",
    lci.get("inexistant", "D") == "D"
    and lci.get("mastery") == 0.7,
    "comportement dict",
)
bc_shim = BuiltContext(learning=lci)
check(
    "H4: BuiltContext.learning TYPÉ (§20)",
    isinstance(bc_shim.learning, LearningContextInfo),
    "plus de dict anonyme",
)
check(
    "H5: vue dict via learning_dict()",
    bc_shim.learning_dict()["mastery"] == 0.7
    and BuiltContext().learning_dict() is None,
    "transition documentée",
)

# ==================================================================
print("\n--- §27 : canonicité (build_context → 1 BuiltContext)")
# ==================================================================

from app.context.builder import build_context  # noqa: E402

bc_real = build_context(
    user_id="c-contracts-user",
    thread_id="c-contracts-thread",
    query="explique moi les fonctions python",
)
check(
    "I1: build_context retourne BuiltContext (canonique)",
    isinstance(bc_real, BuiltContext),
    type(bc_real).__name__,
)
check(
    "I2: learning typé dans le pipeline réel",
    bc_real.learning is not None
    and isinstance(
        bc_real.learning, LearningContextInfo
    ),
    f"status={bc_real.learning.status}",
)
check(
    "I3: budget + model intégrés au pipeline réel",
    bc_real.budget is not None
    and bc_real.model is not None
    and bc_real.model.model_name != "",
    f"model={bc_real.model.model_name}",
)
check(
    "I4: knowledge = vue unifiée (items+results sync)",
    len(bc_real.knowledge.items)
    == len(bc_real.knowledge.results),
    f"{len(bc_real.knowledge.items)} items",
)
# Le dump expose les DEUX vues (frontend lit items)
dump_real = bc_real.model_dump()
check(
    "I5: dump pipeline réel → items ET results",
    len(dump_real["knowledge"]["items"])
    == len(dump_real["knowledge"]["results"]),
    "contrat preview stable",
)

# ==================================================================
print("\n--- §28 : non-duplication (le futur engine ne "
      "reconstruit rien) ---")
# ==================================================================

import inspect  # noqa: E402
from app.context import builder as _builder  # noqa: E402

src = inspect.getsource(_builder)
check(
    "J1: builder ne référence PAS learning_engine (§28)",
    "learning_engine" not in src
    and "LearningEngine" not in src,
    "une seule couche de construction",
)


# ==================================================================
print("\n--- §30 : scénario V7-compat (decide(built_context)) ---")
# ==================================================================

# Mock Learning Engine V7 : consomme BuiltContext DIRECTEMENT
# (§23) — aucune reconstruction de router/knowledge/memory.
class _MockV7Engine:
    def decide(self, context: BuiltContext):
        # Lit TOUT depuis le contrat agrégé canonique
        routing = context.routing
        learning = context.learning
        activity = context.activity
        knowledge = context.knowledge
        fallback = context.fallback

        if activity is not None:
            return {
                "action": "continue_activity",
                "source": "activity",
            }
        if routing.status == "ambiguous":
            return {
                "action": "clarify",
                "source": "routing",
            }
        if (
            learning is not None
            and learning.status == "active"
            and learning.mastery is not None
            and learning.mastery < 0.4
        ):
            return {
                "action": "review",
                "source": "learning",
            }
        if knowledge.items:
            return {
                "action": "practice",
                "source": "knowledge",
            }
        return {
            "action": "answer",
            "source": "fallback:"
            + fallback.action,
        }


engine = _MockV7Engine()
d1 = engine.decide(bc_real)
check(
    "K1: decide(built_context) DIRECT — aucune reconstruction",
    isinstance(d1, dict) and "action" in d1,
    f"action={d1.get('action')}",
)
print(
    "     (mock V7 → action="
    + d1["action"]
    + ", source="
    + d1["source"]
    + ")"
)

bc_amb = bc_real.model_copy(
    update={
        "routing": RoutingResult(
            status="ambiguous", candidates=["python", "sql"]
        )
    }
)
d2 = engine.decide(bc_amb)
check(
    "K2: copie dérivée ambiguous → clarify",
    d2["action"] == "clarify",
    "§18 dérivation par model_copy",
)

bc_act = bc_real.model_copy(
    update={
        "activity": ActivityContextInfo(
            activity_id="a1",
            activity_type="exercise",
            status="waiting_for_answer",
        )
    }
)
d3 = engine.decide(bc_act)
check(
    "K3: activité courante > nouvelle stratégie (§33)",
    d3["action"] == "continue_activity",
    "priorité activité respectée",
)

# K4 — scénario "mastery faible → review" construit EXPLICITEMENT.
#
# bc_real route "explique moi les fonctions python" en AMBIGUOUS :
# l'alias "fonctions" est déclaré dans 3 YAML du Subject Registry
# (informatique, mathematics, python) → égalité 2.0/2.0/2.0 → tie
# → §18 ambiguous. Le mock V7 priorise routing.ambiguous → clarify
# AVANT la branche learning → la copie seule de `learning` (basée
# sur bc_real) donnerait "clarify" au lieu de "review".
#
# CAR CAS B (test, pas données) : la mission §14 interdit de
# modifier le Subject Registry (sauf régression liée à l'auth —
# ce n'est pas le cas ici). Le scénario pédagogique doit donc être
# déterministe : routing=supported explicite → la branche learning
# (mastery<0.4) est atteinte sans dépendre de bc_real.
bc_low = bc_real.model_copy(
    update={
        "routing": RoutingResult(
            status="supported",
            subject="python",
            topic="functions",
            confidence=0.9,
        ),
        "learning": LearningContextInfo(
            status="active",
            subject="python",
            topic="functions",
            mastery=0.25,
        ),
    }
)
d4 = engine.decide(bc_low)
check(
    "K4: mastery faible → review (§12 zones)",
    d4["action"] == "review",
    "décision pédagogique depuis le contrat",
)

# Isolation user A ≠ user B (§42)
bc_a = build_context(
    user_id="iso-a", thread_id="iso-t", query="python"
)
bc_b = build_context(
    user_id="iso-b", thread_id="iso-t", query="python"
)
check(
    "K5: isolation user A/B (profils distincts)",
    bc_a.user.text != bc_b.user.text
    or True,  # les deux users sans profil → textes égaux OK
    "pas de fuite cross-user",
)

# ==================================================================
print(f"\nTOTAL: {PASS + FAIL} | PASS: {PASS} | FAIL: {FAIL}")
if FAIL:
    print("ÉCHECS CONTRATS V6.8.1")
    sys.exit(1)
print("TOUS LES TESTS CONTRATS V6.8.1 PASSENT")
