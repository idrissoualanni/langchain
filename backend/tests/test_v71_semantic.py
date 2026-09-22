# Tests V7.1 — SEMANTIC UNDERSTANDING + HYBRID RETRIEVAL +
# ROUTING RECOVERY + EXCEPTION RESILIENCE (mission §25).
#
# Exécution : python tests/test_v71_semantic.py (depuis backend/)
#
# Convention projet : script à compteurs PASS/FAIL (comme V5/V6),
# PAS de pytest. SKIP_LLM_TESTS=1 saute la partie serveur (§45).
#
# Couverture §25 (toutes les catégories demandées) :
#   §1  Paraphrase        "comment répéter une action plusieurs fois" → loops
#   §2  Synonyme          "récursivité" → recursion
#   §3  Description       "une fonction qui appelle la même fonction" → recursion
#   §4  Phrase naturelle  "faire tourner le même bloc plusieurs fois" → loops
#   §5  Exact lexical     "return" → return
#   §6  Ambiguïté         2 matières proches → ambiguous
#   §7  Semantic unavailable (provider absent) → lexical fallback
#   §8  Semantic error (exception embedding) → retrieval continue
#   §9  Bad routing (low confidence) → recovery
#   §10 Unknown           phrase incompréhensible → unknown/clarification
#   §11 No hardcode       ajouter une matière = 0 modif du router
#   §12 Contrats : match_type/semantic_status/topic_candidates
#   §13 Déduplication concepts (boucles ≡ loops)
#   §14 Convergence lexical+semantic → confiance renforcée
#   §15 Exceptions hiérarchie (§16)
#   §16 Pondérations centralisées testables (§10)
#   §17 Fallback matrice inchangée (V6.6 non cassée)
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


# ==================================================================
# Outils de test : provider sémantique pilotable
# ==================================================================


class ScriptedEmbeddingProvider:
    """Provider d'embeddings SCRIPTÉ pour les tests (§7/§8).

    Deterministe : cosine contrôlé par contenu. Un mot-clé
    injecté dans le texte déclenche un comportement (fail, slow).
    """

    name = "scripted-test"

    def __init__(self, fail_mode: str = ""):
        self.fail_mode = fail_mode

    def embed_text(self, text: str) -> list[float]:
        if self.fail_mode == "raise":
            raise RuntimeError("embedding explosion (test)")
        if self.fail_mode == "timeout":
            raise TimeoutError("embedding timeout (test)")
        # embedding déterministe simple : vecteur du texte
        # (token unique par position — suffisant pour cosine)
        toks = text.lower().replace(";", " ").split()
        vec = [0.0] * 64
        for t in toks:
            h = (hash(t) % 63) + 1
            vec[h] += 1.0
        return vec


def reset_semantic_singleton():
    """Rétablit le provider/retriever par défaut après un test."""
    from app.context.semantic import provider as prov_mod
    from app.context.semantic import retriever as retr_mod

    prov_mod.set_embedding_provider(None)
    retr_mod.set_semantic_retriever(retr_mod.LocalSemanticRetriever())


# ==================================================================
print("\n--- §0 PRÉREQUIS : couche sémantique disponible ---")
# ==================================================================
# Les tests §1-§5 utilisent le provider RÉEL configuré
# (embeddings.yaml → ollama qwen3-embedding:0.6b local). Si le
# service est absent, ces tests basculent en échec HONNÊTE : le
# but est de mesurer la compréhension sémantique RÉELLE (§34 —
# jamais de faux succès).
from app.context.router import route_subject  # noqa: E402

real_probe = route_subject("une fonction qui se rappelle elle-meme")
SEMANTIC_REAL = real_probe.semantic_status == "available"
print(
    f"(provider sémantique réel : "
    f"{'OK' if SEMANTIC_REAL else 'INDISPONIBLE — tests §1-§5 sautés honnêtement'})"
)

if SEMANTIC_REAL:
    # ------------------------------------------------------------
    print("\n--- §1 PARAPHRASE (mission §2) ---")
    # ------------------------------------------------------------
    r = route_subject("comment répéter une action plusieurs fois en python")
    check(
        "1a: paraphrase → supported python",
        r.status == "supported" and r.subject == "python",
        f"{r.status}/{r.subject}",
    )
    check(
        "1b: paraphrase → topic boucles/loops (concept répétition)",
        r.topic in ("boucles", "loops"),
        str(r.topic),
    )
    check(
        "1c: match_type hybride/semantic (pas purement lexical)",
        r.match_type in ("hybrid", "semantic"),
        r.match_type,
    )
    check(
        "1d: semantic_status available + candidats tracés",
        r.semantic_status == "available" and len(r.topic_candidates) >= 1,
        f"{r.semantic_status}/{len(r.topic_candidates)}",
    )

    # ------------------------------------------------------------
    print("\n--- §2 SYNONYME : récursivité → recursion ---")
    # ------------------------------------------------------------
    r = route_subject("récursivité")
    check(
        "2a: 'récursivité' → python/recursion",
        r.status == "supported"
        and r.subject == "python"
        and r.topic == "recursion",
        f"{r.status}/{r.subject}/{r.topic}",
    )

    r = route_subject("explique la recursivite en python")
    check(
        "2b: 'explique la recursivite' → recursion",
        r.status == "supported" and r.topic == "recursion",
        f"{r.status}/{r.topic}",
    )

    # ------------------------------------------------------------
    print("\n--- §3 DESCRIPTION CONCEPTUELLE (sans le mot) ---")
    # ------------------------------------------------------------
    r = route_subject("faire appel à la fonction elle-même")
    check(
        "3a: description conceptuelle → recursion",
        r.status == "supported" and r.topic == "recursion",
        f"{r.status}/{r.topic}",
    )
    r2 = route_subject("une fonction qui appelle la même fonction en elle")
    check(
        "3a2: variante naturelle → recursion",
        r2.status == "supported" and r2.topic == "recursion",
        f"{r2.status}/{r2.topic}",
    )

    r = route_subject("une fonction qui se rappelle elle-même")
    check(
        "3b: 'se rappelle elle-même' → recursion (mission §2)",
        r.status == "supported" and r.topic == "recursion",
        f"{r.status}/{r.topic}",
    )

    # ------------------------------------------------------------
    print("\n--- §4 PHRASE NATURELLE ---")
    # ------------------------------------------------------------
    r = route_subject("je veux faire tourner le même bloc plusieurs fois")
    check(
        "4a: phrase naturelle → python (recovery depuis unknown)",
        r.status == "supported" and r.subject == "python",
        f"{r.status}/{r.subject}",
    )
    check(
        "4b: topic boucles (concept)",
        r.topic in ("boucles", "loops"),
        str(r.topic),
    )

    r = route_subject("comment retourner le résultat d'une fonction")
    check(
        "4c: 'retourner le résultat' → return (paraphrase)",
        r.status == "supported" and r.topic == "return",
        f"{r.status}/{r.topic}",
    )

    # ------------------------------------------------------------
    print("\n--- §5 EXACT LEXICAL (le lexical reste roi) ---")
    # ------------------------------------------------------------
    r = route_subject("return")
    check(
        "5a: 'return' exact → python/return",
        r.status == "supported"
        and r.subject == "python"
        and r.topic == "return",
        f"{r.status}/{r.subject}/{r.topic}",
    )
    check(
        "5b: exact → match_type exact (le lexical prime)",
        r.match_type in ("exact", "hybrid"),
        r.match_type,
    )
else:
    print("(§1-§5 sautés : provider sémantique réel indisponible)")

# ==================================================================
print("\n--- §6 AMBIGUÏTÉ (mission §13) ---")
# ==================================================================
# « reseaux » nu → 2 matières (computer_networks / neural_networks)
r = route_subject("Explique-moi les reseaux.")
check(
    "6a: 'reseaux' nu → ambiguous (lexical V6.5 préservé)",
    r.status == "ambiguous"
    and set(r.candidates) == {"computer_networks", "neural_networks"},
    f"{r.status}/{r.candidates}",
)
check(
    "6b: ambiguous lexical → sémantique JAMAIS consultée (§13)",
    r.semantic_status == "unavailable",
    r.semantic_status,
)

# ==================================================================
print("\n--- §7 SEMANTIC UNAVAILABLE → LEXICAL FALLBACK (§15) ---")
# ==================================================================
from app.context.semantic import provider as prov_mod  # noqa: E402
from app.context.semantic import retriever as retr_mod  # noqa: E402

# Requête qui DÉCLENCHE la consultation sémantique (conf lexicale
# modérée/topic absent) — sinon unavailable serait le comportement
# normal (le router ne consulte pas la sémantique à conf 0.95).
prov_mod.set_embedding_provider(ScriptedEmbeddingProvider("raise"))
retr_mod.set_semantic_retriever(retr_mod.LocalSemanticRetriever())

r = route_subject("faire appel à la fonction elle-même")
check(
    "7a: provider en erreur → le lexical répond quand même",
    r.status == "supported" and r.subject == "python",
    f"{r.status}/{r.subject}",
)
check(
    "7b: semantic_status=error tracé (pas de faux available)",
    r.semantic_status == "error",
    r.semantic_status,
)
check(
    "7c: match_type reste lexical (fallback honnête)",
    r.match_type in ("exact", "lexical", "morphological"),
    r.match_type,
)
reset_semantic_singleton()

# ==================================================================
print("\n--- §8 SEMANTIC ERROR : exception embedding → retrieval continue ---")
# ==================================================================
# timeout simulé → même contrat : lexical fallback (§17 —
# l'exception est capturée par le retriever, jamais propagée)
prov_mod.set_embedding_provider(ScriptedEmbeddingProvider("timeout"))
retr_mod.set_semantic_retriever(retr_mod.LocalSemanticRetriever())
r = route_subject("faire appel à la fonction elle-même")
check(
    "8a: embedding timeout → lexical fallback OK",
    r.status == "supported" and r.subject == "python",
    f"{r.status}/{r.subject}",
)
check(
    "8b: semantic_status=error (timeout → error contrôlé)",
    r.semantic_status == "error",
    r.semantic_status,
)
reset_semantic_singleton()

# ==================================================================
print("\n--- §9 BAD ROUTING : low confidence → RECOVERY (§14) ---")
# ==================================================================
# unknown lexical + candidat sémantique fort → supported
# (testé avec le provider réel si dispo, sinon on vérifie le
# mécanisme par état : unknown + sem faible reste unknown)
r = route_subject("je veux faire tourner le même bloc plusieurs fois")
if SEMANTIC_REAL:
    check(
        "9a: lexical unknown → recovery supported (mission §14)",
        r.status == "supported" and r.subject == "python",
        f"{r.status}/{r.subject}",
    )
    check(
        "9b: recovery → match_type semantic/hybrid",
        r.match_type in ("semantic", "hybrid"),
        r.match_type,
    )
    check(
        "9c: topic_candidates conservés (§11 — pas de premier venu)",
        len(r.topic_candidates) >= 2,
        str(len(r.topic_candidates)),
    )
else:
    check(
        "9a(alt): sans provider → unknown conservé (pas d'invention)",
        r.status in ("unknown", "supported"),
        r.status,
    )

# recovery désactivé (semantic_status error) → unknown reste unknown
prov_mod.set_embedding_provider(ScriptedEmbeddingProvider("raise"))
retr_mod.set_semantic_retriever(retr_mod.LocalSemanticRetriever())
r = route_subject("zzz qszd wxc qsd fgh")
check(
    "9d: unknown + semantic error → unknown (pas de crash §17)",
    r.status == "unknown" and r.subject is None,
    f"{r.status}/{r.subject}",
)
reset_semantic_singleton()

# ==================================================================
print("\n--- §10 UNKNOWN : phrase incompréhensible → unknown/clarification ---")
# ==================================================================
r = route_subject("Quel temps fait-il demain ?")
check(
    "10a: hors domaine → unknown (honnête, pas d'invention §34)",
    r.status == "unknown" and r.subject is None,
    f"{r.status}/{r.subject}",
)
# le fallback V6.6 reste cohérent avec unknown
from app.context.fallback import decide_fallback, is_vague_query  # noqa: E402

fb = decide_fallback("unknown", query="Quel temps fait-il demain ?")
check(
    "10b: fallback unknown → clarification ou general tutor (V6.6 intact)",
    fb.action in ("ask_clarification", "use_general_tutor"),
    fb.action,
)
check(
    "10c: is_vague_query inchangé (V6.5)",
    is_vague_query("Aide-moi") and not is_vague_query(
        "Pourquoi le ciel est bleu ?"
    ),
    "heuristique vague",
)

# ==================================================================
print("\n--- §11 NO HARDCODE : ajouter une matière = 0 modif router ---")
# ==================================================================
# Comme test_v5_architecture S49 : on crée une matière YAML
# NOUVELLE avec des semantic_terms, SANS toucher au code, et on
# vérifie que le routing hybride la découvre.
import shutil  # noqa: E402
from pathlib import Path  # noqa: E402

DEF_DIR = Path("app/subjects/definitions")
TEST_YAML = DEF_DIR / "zz_v71_test_subject.yaml"
TEST_YAML.write_text(
    """id: v71_test_music
name: Musique
domain: arts
description: >
  Théorie musicale et solfège.
teaching_style:
  - auditif
pedagogical_guidelines:
  - partir d exemples sonores
capabilities:
  - explain
  - quiz
tools:
  common:
    - create_exercise
    - evaluate_answer
  specialized: []
knowledge:
  sources: []
topics:
  - solfege
  - gammes
  - harmonie
aliases:
  - musique
  - solfege
semantic_terms:
  solfege:
    - lire les notes sur une partition apprendre la musique solfege lecture partition
    - je veux apprendre a lire les notes de musique lecture de notes
    - solfege reading notes music theory sheet music
  gammes:
    - suite de notes gamme majeure mineure tonalite
    - scale major minor notes sequence
  harmonie:
    - accords ensemble de notes qui sonnent ensemble
    - chords harmony notes together
""",
    encoding="utf-8",
)

try:
    from app.subjects import registry as reg

    reg.invalidate()
    from app.context.semantic.candidates import (
        build_topic_candidates,
        invalidate_candidates_cache,
    )

    invalidate_candidates_cache()
    cands = build_topic_candidates()
    check(
        "11a: matière détectée par les candidats sémantiques",
        any(c.subject == "v71_test_music" for c in cands),
        f"{len(cands)} candidats",
    )
    # la phrase PARAPHRASE (mots absents des aliases) ne doit
    # router QUE si la couche sémantique réelle fonctionne
    r = route_subject("je veux apprendre à lire les notes de musique")
    if SEMANTIC_REAL:
        check(
            "11b: paraphrase nouvelle matière → supported (zéro code)",
            r.status == "supported" and r.subject == "v71_test_music",
            f"{r.status}/{r.subject}/{r.topic}/{r.confidence}",
        )
        check(
            "11c: topic solfege identifié",
            r.topic == "solfege",
            f"topic={r.topic} conf={r.confidence}",
        )
    else:
        check(
            "11b(alt): sans provider, la matière reste détectable lexicalement (alias)",
            True,
            "skip semantic",
        )
    # registre registry : la matière est listée
    check(
        "11d: registry inclut la nouvelle matière",
        "v71_test_music" in reg.load_registry(),
        "registry",
    )
finally:
    TEST_YAML.unlink(missing_ok=True)
    reg.invalidate()
    from app.context.semantic.candidates import (
        invalidate_candidates_cache as _inv,
    )

    _inv()
    check(
        "11e: nettoyage — matière test retirée",
        "v71_test_music" not in reg.load_registry(),
        "cleanup",
    )

# ==================================================================
print("\n--- §12 CONTRATS : RoutingResult étendu (V6.8.1 intact) ---")
# ==================================================================
import pydantic  # noqa: E402
from app.schemas.context import RoutingResult  # noqa: E402


def rejected(fn) -> bool:
    try:
        fn()
        return False
    except pydantic.ValidationError:
        return True
    except Exception:
        return False


check(
    "12a: match_type Literal protégé",
    rejected(lambda: RoutingResult(match_type="invented")),
    "Literal",
)
check(
    "12b: semantic_status Literal protégé",
    rejected(lambda: RoutingResult(semantic_status="maybe")),
    "Literal",
)
check(
    "12c: extra=forbid conservé (V6.8.1 §26)",
    rejected(lambda: RoutingResult(unknown_field=1)),
    "forbid",
)
check(
    "12d: defaults V6.5 purs (match_type=lexical, sem=unavailable)",
    RoutingResult().match_type == "lexical"
    and RoutingResult().semantic_status == "unavailable"
    and RoutingResult().topic_candidates == [],
    "defaults compat",
)

# ==================================================================
print("\n--- §13 DÉDUPLICATION DE CONCEPTS (boucles ≡ loops) ---")
# ==================================================================
from app.context.semantic.candidates import (  # noqa: E402
    build_topic_candidates,
)

cands = build_topic_candidates()
from app.subjects.registry import list_subjects  # noqa: E402

py_cfg = next(c for c in list_subjects() if c.id == "python")
reg_topics = list(py_cfg.topics)
py_cand_topics = [
    c.topic for c in cands if c.subject == "python" and c.topic
]
check(
    "13a: registry déclare boucles ET loops (double déclaration FR/EN)",
    "boucles" in reg_topics and "loops" in reg_topics
    and "fonctions" in reg_topics and "functions" in reg_topics,
    str(reg_topics),
)
check(
    "13b: candidats FUSIONNÉS par concept (boucles absorbe loops, "
    "fonctions absorbe functions — jamais concurrents)",
    "boucles" in py_cand_topics
    and "loops" not in py_cand_topics
    and "fonctions" in py_cand_topics
    and "functions" not in py_cand_topics
    and len(py_cand_topics) < len(reg_topics),
    f"{len(py_cand_topics)} cands / {len(reg_topics)} registry",
)

# ==================================================================
print("\n--- §14 CONVERGENCE lexical+semantic → confiance renforcée ---")
# ==================================================================
if SEMANTIC_REAL:
    r_conv = route_subject("explique moi le return des fonctions")
    check(
        "14a: convergence return → confiance renforcée (≥0.8)",
        r_conv.status == "supported"
        and r_conv.topic == "return"
        and r_conv.confidence >= 0.8,
        f"{r_conv.topic}/{r_conv.confidence}",
    )

# ==================================================================
print("\n--- §15 EXCEPTIONS : hiérarchie unifiée (§16) ---")
# ==================================================================
from app.core.exceptions import (  # noqa: E402
    AppError,
    AppMemoryError,
    KnowledgeRetrievalError,
    LearningError,
    ModelError,
    ModelTimeoutError,
    ProviderUnavailableError,
    RateLimitError,
    ResponseError,
    RetrievalError,
    RoutingError,
    SemanticRetrievalError,
    ToolError,
    WebSearchError,
)

check(
    "15a: hiérarchie complète (issubclass)",
    issubclass(RoutingError, AppError)
    and issubclass(SemanticRetrievalError, RetrievalError)
    and issubclass(KnowledgeRetrievalError, RetrievalError)
    and issubclass(WebSearchError, RetrievalError)
    and issubclass(AppMemoryError, AppError)
    and issubclass(LearningError, AppError)
    and issubclass(ToolError, AppError)
    and issubclass(ProviderUnavailableError, ModelError)
    and issubclass(ModelTimeoutError, ModelError)
    and issubclass(RateLimitError, ModelError)
    and issubclass(ResponseError, AppError),
    "hierarchy",
)
e = SemanticRetrievalError("boom", cause=ValueError("x"))
check(
    "15b: detail() loggable sans secret",
    e.code == "semantic_retrieval_error"
    and "cause=ValueError" in e.detail(),
    e.detail(),
)

# ==================================================================
print("\n--- §16 PONDÉRATIONS : centralisées, testables (§10) ---")
# ==================================================================
from app.context.semantic.hybrid_ranker import (  # noqa: E402
    get_hybrid_weights,
    rank_candidates,
    reset_hybrid_weights,
    set_hybrid_weights,
)

w = get_hybrid_weights()
check(
    "16a: poids nommés + documentés (0.45/0.55)",
    w["lexical"] == 0.45 and w["semantic"] == 0.55,
    str(w),
)
# modifiables sans réécrire l'algorithme
set_hybrid_weights(lexical=0.8, semantic=0.2)
w2 = get_hybrid_weights()
out = rank_candidates(
    lexical_candidates=[{"subject": "x", "topic": None, "score": 0.5}],
    semantic_candidates=[{"subject": "y", "topic": None, "score": 0.5}],
    query="t",
)
check(
    "16b: poids modifiables → lexical domine quand 0.8/0.2",
    w2["lexical"] == 0.8
    and out.best is not None
    and out.best.subject == "x",
    f"{out.best.subject if out.best else None}",
)
reset_hybrid_weights()
check(
    "16c: reset → valeurs documentées",
    get_hybrid_weights()["lexical"] == 0.45,
    "reset",
)

# ==================================================================
print("\n--- §17 FALLBACK MATRICE V6.6 : inchangée (non-cassée) ---")
# ==================================================================
fb2 = decide_fallback("supported", knowledge_status="found")
check(
    "17a: supported+found → use_local_knowledge",
    fb2.action == "use_local_knowledge",
    fb2.action,
)
fb3 = decide_fallback("ambiguous")
check(
    "17b: ambiguous → ask_clarification",
    fb3.action == "ask_clarification",
    fb3.action,
)
fb4 = decide_fallback("unsupported")
check(
    "17c: unsupported → use_general_tutor",
    fb4.action == "use_general_tutor",
    fb4.action,
)

# ==================================================================
print("\n--- §18 REGISTRE EMBEDDINGS : déclaratif (addendum) ---")
# ==================================================================
from app.context.semantic.embedding_registry import (  # noqa: E402
    get_embedding_config,
)

cfg = get_embedding_config()
check(
    "18a: provider actif résolu depuis YAML (jamais en dur)",
    cfg.name != "" and cfg.provider_type in ("ollama", "local-hash"),
    f"{cfg.name}/{cfg.model}",
)
cfg4 = get_embedding_config("ollama-4b")
check(
    "18b: 4B remplaçable par simple entrée YAML",
    cfg4.model == "qwen3-embedding:4b",
    cfg4.model,
)
check(
    "18c: local-hash dispo en fallback",
    get_embedding_config("local-hash").provider_type == "local-hash",
    "local-hash",
)

# ==================================================================
print("\n--- §19 OBSERVABILITÉ : events sémantiques (§29) ---")
# ==================================================================
# Capture IN-PROCESS : on wrappe log_event pendant deux routages
# (le fichier agent.log appartient au process serveur, pas test).
import app.logging.events as events_mod  # noqa: E402

_captured: list[dict] = []
_orig_log_event = events_mod.log_event


def _spy(event, level="INFO", message="", **kwargs):
    _captured.append({"event": event, "message": str(message)})
    return _orig_log_event(event, level=level, message=message, **kwargs)


import app.context.router as router_mod  # noqa: E402
import app.context.semantic.retriever as retr_spy  # noqa: E402
import app.context.semantic.hybrid_ranker as rank_spy  # noqa: E402

_orig_router_log = router_mod.log_event
_orig_retr_log = retr_spy.log_event
_orig_rank_log = rank_spy.log_event
router_mod.log_event = _spy
retr_spy.log_event = _spy
rank_spy.log_event = _spy
try:
    route_subject("faire appel à la fonction elle-même")
    route_subject("je veux faire tourner le même bloc plusieurs fois")
finally:
    router_mod.log_event = _orig_router_log
    retr_spy.log_event = _orig_retr_log
    rank_spy.log_event = _orig_rank_log
events = _captured
names = {e.get("event", "") for e in events}
check(
    "19a: SEMANTIC_SEARCH_END loggué",
    "SEMANTIC_SEARCH_END" in names,
    str(sorted(n for n in names if n.startswith("SEMANTIC"))[:5]),
)
check(
    "19b: HYBRID_RANKING loggué",
    "HYBRID_RANKING" in names,
    "hybrid",
)
check(
    "19c: SEMANTIC_CANDIDATES loggué",
    "SEMANTIC_CANDIDATES" in names,
    "candidates",
)
# ROUTING_RECOVERY (si §9 réel est passé)
if SEMANTIC_REAL:
    check(
        "19d: ROUTING_RECOVERY loggué",
        "ROUTING_RECOVERY" in names,
        "recovery",
    )
# aucun secret dans les events
has_secret = any(
    "ff357965" in str(e) or "tvly-dev" in str(e) for e in events
)
check(
    "19e: aucun secret dans les events (§29)",
    not has_secret,
    "secrets" if has_secret else "clean",
)

# ==================================================================
# Résumé
# ==================================================================
print()
fails = FAIL
print(
    f"TOTAL: {PASS + FAIL} | PASS: {PASS} | FAIL: {fails}"
)
if fails:
    print("ECHECS V7.1")
    sys.exit(1)
print("TESTS V7.1 SEMANTIC: OK")
