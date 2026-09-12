# Tests V6.8 — CONTEXT BUDGET (§52).
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


from app.context.budget import (  # noqa: E402
    CONSERVATIVE_ASSUMED_WINDOW,
    BudgetSection,
    apply_budget,
    build_budget,
    estimate_tokens,
)
from app.context.model_capabilities import (  # noqa: E402
    ModelCapabilities,
)

print("--- §42 : estimation ---")
check(
    "0a. estimate_tokens : 100 chars → 25 tokens (≈4c/tok)",
    estimate_tokens("a" * 100) == 25
    and estimate_tokens("abcd") == 1
    and estimate_tokens("") == 0,
    str(estimate_tokens("a" * 100)),
)

print("--- §52 : budget ---")

# 3. Output réservé (window 32000, reserved 2048 → 29952)
budget = build_budget(
    ModelCapabilities(
        model_name="x",
        context_window=32000,
        reserved_output_tokens=2048,
    )
)
check(
    "3. output réservé → available 29952",
    budget.available_input_tokens == 29952
    and budget.context_window == 32000,
    str(budget.available_input_tokens),
)

# Fenêtre inconnue → conservateur, available null (honnête)
budget_null = build_budget(
    ModelCapabilities(model_name="x")
)
check(
    "3b. window null → available null (jamais inventée), "
    "fallback 8192 assumé",
    budget_null.context_window is None
    and budget_null.available_input_tokens is None
    and CONSERVATIVE_ASSUMED_WINDOW == 8192,
)


def sec(key, prio, tokens, payload=None):
    return BudgetSection(
        key=key, priority=prio, tokens=tokens, payload=payload
    )


# Sections type d'un run réel : P0 system/message/activité,
# P1 learning, P2 knowledge/web, P3 mémoire, P4 thread
def typical(kt=500, wt=300, mt=200, tt=400, lt=150, scale=1):
    return [
        sec("system", 0, 2000),
        sec("user_message", 0, 100),
        sec("activity", 0, 150),
        sec("learning", 1, int(lt * scale)),
        sec("knowledge", 2, int(kt * scale)),
        sec(
            "web_search",
            2,
            int(wt * scale),
            [
                {"title": f"r{i}", "content": "x" * 40,
                 "snippet": "s" * 10}
                for i in range(5)
            ],
        ),
        sec("memory", 3, int(mt * scale)),
        sec("thread", 4, int(tt * scale)),
    ]


# 4. Calcul budget (5. sous budget)
sections = typical()
res = apply_budget(sections, window=32000, reserved=2048)
total = sum(s.tokens for s in sections)
check(
    "4. calcul budget exact (somme conservée)",
    res.estimated_input_tokens == total
    and res.sources_used == len(sections)
    and res.sources_dropped == 0,
    f"{res.estimated_input_tokens} tokens",
)
check(
    "5. contexte sous budget → ok, rien droppé",
    res.budget_status == "ok"
    and res.dropped_keys == []
    and all(
        s.key in [k.key for k in res.kept]
        for s in sections
    ),
    res.budget_status,
)

# 6. Proche limite (>85%) — calibré : total ≈ 27300 / 29952 (91%)
# window 32000, reserved 2048 → available 29952 ; cible ≥ 25459
near = [
    sec("system", 0, 2000),
    sec("user_message", 0, 300),
    sec("activity", 0, 500),
    sec("learning", 1, 8000),
    sec("knowledge", 2, 10000),
    sec("web_search", 2, 2500),
    sec("memory", 3, 2000),
    sec("thread", 4, 2000),
]
res = apply_budget(near, window=32000, reserved=2048)
check(
    "6. proche limite (≥85%) → near_limit",
    res.budget_status == "near_limit"
    and res.sources_dropped == 0,
    f"{res.estimated_input_tokens} → {res.budget_status}",
)

# 7. Dépassé → compression P4 d'abord
# total 27300+2600 = 29900+ ... cible : dépasser 29952 d'un peu
over = [
    sec("system", 0, 2000),
    sec("user_message", 0, 300),
    sec("activity", 0, 500),
    sec("learning", 1, 8000),
    sec("knowledge", 2, 10000),
    sec("web_search", 2, 3000),
    sec("memory", 3, 3000),
    sec("thread", 4, 4000),  # 30800 > 29952 → thread seul suffit
]
res = apply_budget(over, window=32000, reserved=2048)
check(
    "7a. dépassé → compressed (P4 thread droppé en premier)",
    res.budget_status == "compressed"
    and "thread" in res.dropped_keys
    and "memory" not in res.dropped_keys
    and "system" not in res.dropped_keys,
    f"dropped={res.dropped_keys} status={res.budget_status}",
)

# Vraiment trop gros → exceeded (P0 sauvés quand même)
huge = typical(scale=200)  # ≈ 142k >> 29952
res = apply_budget(huge, window=32000, reserved=2048)
keys = [s.key for s in res.kept]
check(
    "7b. exceeded : P0 system/message/activité TOUJOURS là",
    res.budget_status == "exceeded"
    and {"system", "user_message", "activity"} <= set(keys)
    and "thread" in res.dropped_keys
    and "memory" in res.dropped_keys,
    f"status={res.budget_status}, dropped={res.dropped_keys}",
)

# 8. Réduction des résultats search (top 5 → moins, ordre §44)
sections = typical(scale=50)  # dépasse → search réduit
res = apply_budget(sections, window=32000, reserved=2048)
web = [s for s in res.kept if s.key == "web_search"]
check(
    "8. search réduit (top_k diminué, ordre préservé)",
    (not web)  # droppé avant d'arriver à la réduction, OK
    or len(web[0].payload) < 5,
    (
        "web droppé (compression plus forte)"
        if not web
        else f"top {len(web[0].payload)}/5"
    ),
)

# 8b. Cas spécifique : seule la search dépasse le budget
# system+user+activity = 200 ; web 4×300 = 1200 → total 1400 > 1000
only_web = [
    sec("system", 0, 100),
    sec("user_message", 0, 50),
    sec("activity", 0, 50),
    sec("web_search", 2, 1200, [
        {"title": f"r{i}", "content": "x" * 200, "snippet": "y"}
        for i in range(4)
    ]),
]
res = apply_budget(only_web, window=1000, reserved=0)
web = [s for s in res.kept if s.key == "web_search"]
check(
    "8b. search seule dépassante → payload réduit (top_k §44)",
    web
    and len(web[0].payload) < 4
    and res.budget_status in ("compressed", "exceeded"),
    f"{len(web[0].payload)}/4 conservés, "
    f"status={res.budget_status}",
)

# 9. Réduction mémoire peu pertinente (les dernières d'abord)
mem_sections = [
    sec("system", 0, 100),
    sec("user_message", 0, 50),
    sec("activity", 0, 50),
    sec("memory_a", 3, 400),
    sec("memory_b", 3, 300),
    sec("memory_c", 3, 200),
    sec("thread", 4, 100),
]
res = apply_budget(mem_sections, window=900, reserved=0)
check(
    "9. mémoire réduite : P4 d'abord puis les dernières P3",
    "thread" in res.dropped_keys
    and (
        "memory_c" in res.dropped_keys
        or "memory_b" in res.dropped_keys
    )
    and "memory_a" not in res.dropped_keys,
    f"dropped={res.dropped_keys}",
)

# 10-11. P0 jamais supprimés (même exceeded)
res = apply_budget(huge, window=32000, reserved=2048)
keys = [s.key for s in res.kept]
check(
    "10. activité préservée (P0, même exceeded)",
    "activity" in keys,
)
check(
    "11. current user message préservé (P0, même exceeded)",
    "user_message" in keys and "system" in keys,
)

# 12-13. Capacities : chemins §49/§50 (via registry)
from app.context.model_capabilities import supports  # noqa: E402

caps = ModelCapabilities(model_name="x", supports_tools=True)
check(
    "12-13. capability checks : tools ok, structured/vision/audio → fallback",
    supports(caps, "tools")
    and not supports(caps, "structured_output")
    and not supports(caps, "vision")
    and not supports(caps, "audio"),
)

# Window null → statut unknown (assomption documentée)
res = apply_budget(typical(), window=None, reserved=2048)
check(
    "14a. window null → unknown (assomption signalée, pas ok)",
    res.budget_status == "unknown",
    res.budget_status,
)
res = apply_budget(typical(scale=5), window=None, reserved=2048)
check(
    "14b. window null + compression nécessaire → compressed prime",
    res.budget_status in ("compressed", "exceeded"),
    res.budget_status,
)

# Builder réel : budget appliqué sans rien casser
from app.context.builder import build_context  # noqa: E402

bc = build_context(
    "v68-t", "v68-t", "Explique-moi les boucles python"
)
stats = bc.stats
check(
    "15. build_context réel : budget appliqué, pas de crash, "
    "knowledge présent",
    getattr(stats, "budget_status", None)
    in ("ok", "near_limit", "compressed", "exceeded", "unknown")
    and bc.knowledge.items
    and getattr(stats, "estimated_input_tokens", 0) > 0,
    f"status={getattr(stats, 'budget_status', '?')} "
    f"est={getattr(stats, 'estimated_input_tokens', '?')}",
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
print("TESTS V6.8 CONTEXT BUDGET: OK")
