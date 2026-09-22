# Test final §60 — PRÉPARATION LEARNING ENGINE.
#
# Montre que TOUTES les informations nécessaires au futur V7
# sont disponibles dans un seul BuiltContext, SANS créer le
# Learning Engine (§58/§59 : le profil reste une SOURCE, aucune
# décision pédagogique automatique).
#
# User + Thread + Subject + Topic + Knowledge + Search + Fallback
# + Memory + Learning Profile + Activity + Model capabilities
# + Context budget.
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


from app.services.context.builder import build_context  # noqa: E402

bc = build_context(
    user_id="v68-final",
    thread_id="v68-final",
    query="Explique-moi les boucles python avec des exemples",
)

print("--- §60 : disponibilité des informations V7 ---")

# 1. USER
check(
    "User (memory context présent)",
    bc.user is not None and hasattr(bc.user, "text"),
)

# 2. THREAD
check(
    "Thread (state du thread présent)",
    bc.thread is not None and hasattr(bc.thread, "thread_id"),
)

# 3-4. SUBJECT + TOPIC (routing)
check(
    "Subject routé (python)",
    bc.routing.subject == "python",
    bc.routing.subject or "?",
)
check(
    "Topic routé + confidence graduée",
    bc.routing.topic is not None
    and 0.0 <= bc.routing.confidence <= 1.0,
    f"{bc.routing.topic} @ {bc.routing.confidence}",
)

# 5. KNOWLEDGE
check(
    "Knowledge local (found pour boucles)",
    bc.knowledge.status == "found" and bc.knowledge.items,
    f"{bc.knowledge.status}, {len(bc.knowledge.items)} items",
)

# 6. SEARCH (web — attempted ou non, mais structuré)
check(
    "Search web structuré (SearchResponse)",
    bc.web is not None
    and bc.web.status
    in ("found", "insufficient", "unavailable", "error"),
    bc.web.status,
)

# 7. FALLBACK (décision V6.6)
check(
    "Fallback decision présente (5 actions possibles)",
    bc.fallback is not None
    and bc.fallback.action
    in (
        "use_local_knowledge",
        "use_web_search",
        "ask_clarification",
        "use_general_tutor",
        "continue_without_external_search",
    ),
    bc.fallback.action,
)

# 8. MEMORY (user memory sélectionnée par pertinence)
check(
    "User memory (liste, éventuellement vide = honnête)",
    isinstance(bc.relevant_memories, list),
    f"{len(bc.relevant_memories)} items",
)

# 9. LEARNING PROFILE (V6 — source de progression, §58)
# V6.8.1 §20 : learning est TYPÉ (LearningContextInfo) —
# le shim .get() maintient la lecture historique.
learning = bc.learning or None
check(
    "Learning Profile présent (source, pas engine §58)",
    learning is not None
    and learning.get("status") in ("active", "not_started"),
    f"status={learning.get('status')}, "
    f"mastery={learning.get('mastery')}",
)

# 10. ACTIVITY (état pédagogique thread-local — séparé du profil)
# Lu depuis le snapshot LangGraph du thread (comme l'API activity).
from app.schemas.activity import (  # noqa: E402
    summarize_activity,
)
from app.graph.main import get_agent  # noqa: E402

snapshot = get_agent().get_state(
    {
        "configurable": {
            "thread_id": bc.thread.thread_id,
            "user_id": bc.thread.thread_id,
        }
    }
)
values = (snapshot.values or {}) if snapshot else {}
activity = values.get("learning_activity") or {}
act = summarize_activity(activity)
check(
    "Activity thread-local (dict avec status)",
    isinstance(act, dict) and "status" in act,
    str(act.get("status")),
)

# 11. MODEL CAPABILITIES (V6.8)
from app.schemas.model_capabilities import (  # noqa: E402
    get_model_capabilities,
    supports,
)

caps = get_model_capabilities()
check(
    "Model capabilities (provider/model/outils/structured)",
    caps.provider == "ollama"
    and caps.model_name
    and isinstance(caps.supports_tools, bool)
    and isinstance(caps.supports_structured_output, bool),
    f"{caps.provider}/{caps.model_name} tools="
    f"{caps.supports_tools} structured="
    f"{caps.supports_structured_output}",
)

# 12. CONTEXT BUDGET (V6.8)
stats = bc.stats
check(
    "Context budget dans stats (estimation + statut)",
    getattr(stats, "budget_status", None)
    in ("ok", "near_limit", "compressed", "exceeded", "unknown"),
    f"budget={getattr(stats, 'budget_status', '?')} "
    f"est={getattr(stats, 'estimated_input_tokens', '?')}",
)

print("--- §58/§59 : garde-fous Learning Engine ---")

# Le profil est une SOURCE : mastery/mastery_level/weak_points
# lisibles mais AUCUNE décision automatique n'existe (aucun
# module learning_engine, aucune action "fais un exercice").
learning = bc.learning or {}
has_progression_fields = (
    "mastery" in learning
    or "weak_points" in learning
    or learning.get("status") == "not_started"
)
check(
    "Profil = source de progression (champs lisibles)",
    has_progression_fields,
)

import importlib.util  # noqa: E402

# V7 : le Learning Engine EXISTE désormais — le garde-fou §58 de
# V6.8 (aucun engine AVANT l'unification des contrats) devient :
# l'engine est une COUCHE DE DÉCISION PURE (§4.1) — elle n'écrit
# JAMAIS le profil et ne recrée NI router NI recherche.
engine_spec = importlib.util.find_spec("app.services.learning.engine")
if engine_spec is not None:
    import inspect  # noqa: E402

    from app.services.learning import engine as _engine  # noqa: E402

    _src = inspect.getsource(_engine)
    check(
        "Engine V7 : n'écrit PAS le profil (§4.1 lecture seule)",
        "write_learning_profile" not in _src
        and "update_profile_from_observation" not in _src,
    )
    check(
        "Engine V7 : ne recrée PAS router/recherche (§17/§18)",
        "route_subject" not in _src
        and "web_search(" not in _src
        and "search_knowledge(" not in _src,
    )
    check(
        "Engine V7 : consomme BuiltContext (§26)",
        "from app.schemas.context import BuiltContext" in _src,
    )
else:
    check(
        "AUCUN Learning Engine avant V7 (§2 — phases suivantes)",
        True,
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
print("TEST FINAL PREPARATION LEARNING ENGINE: OK")
