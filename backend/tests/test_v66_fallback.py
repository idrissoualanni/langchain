# Tests V6.6 — FALLBACK INTELLIGENCE (§15).
# Matrice de décision pure, événements, transparence, no-crash.
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


from app.services.context.fallback import (  # noqa: E402
    decide_fallback,
    fallback_note_for_prompt,
    is_vague_query,
)
from app.schemas.context import FallbackDecision  # noqa: E402
from app.logging.events import setup_logging  # noqa: E402

setup_logging()  # handler fichier requis pour lire les events

print("--- §6 MATRICE DE DÉCISION (pure, sans LLM) ---")

# 1. supported + knowledge found
d = decide_fallback("supported", knowledge_status="found")
check(
    "1. supported+found → use_local_knowledge",
    d.action == "use_local_knowledge",
    d.action,
)

# 2. supported + knowledge insufficient → web
d = decide_fallback(
    "supported",
    knowledge_status="insufficient",
    web_status="found",
    has_web_results=True,
)
check(
    "2. supported+insufficient+web found → use_web_search",
    d.action == "use_web_search",
    d.action,
)

# 3/4. web unavailable / error → general tutor
for ws in ("unavailable", "error"):
    d = decide_fallback(
        "supported",
        knowledge_status="insufficient",
        web_status=ws,
        has_web_results=False,
    )
    check(
        f"3/4. web {ws} → use_general_tutor",
        d.action == "use_general_tutor",
        d.action,
    )

# 5. ambiguous → clarification
d = decide_fallback("ambiguous")
check(
    "5. ambiguous → ask_clarification",
    d.action == "ask_clarification",
    d.action,
)

# 6. unknown : vague vs compréhensible (§9)
d_vague = decide_fallback("unknown", query="Aide-moi")
d_clair = decide_fallback(
    "unknown", query="Pourquoi le ciel est bleu ?"
)
check(
    "6a. unknown vague ('Aide-moi') → clarification",
    d_vague.action == "ask_clarification",
    d_vague.action,
)
check(
    "6b. unknown compréhensible → general tutor",
    d_clair.action == "use_general_tutor",
    d_clair.action,
)
check(
    "6c. is_vague_query heuristique documentée",
    is_vague_query("Aide-moi")
    and not is_vague_query("Pourquoi le ciel est bleu ?"),
)

# 7. unsupported → general tutor
d = decide_fallback("unsupported", subject="astrophysique")
check(
    "7. unsupported → use_general_tutor",
    d.action == "use_general_tutor",
    d.action,
)

# 8. multi_domain → clarification
d = decide_fallback("multi_domain")
check(
    "8. multi_domain → ask_clarification",
    d.action == "ask_clarification",
    d.action,
)

# 9. NO CRASH : statut inattendu, valeurs absurdes
try:
    d = decide_fallback("", knowledge_status="", web_status="")
    no_crash = d.action == "continue_without_external_search"
except Exception as exc:  # pragma: no cover
    no_crash = False
check(
    "9. statut inattendu → continue sans crash",
    no_crash,
    d.action if no_crash else "CRASH",
)

# 10. FALLBACK events émis — lus depuis agent.log (fichier,
# indépendant du loop asyncio : testable hors serveur)
from app.logging.events import read_log_file  # noqa: E402

d = decide_fallback(
    "supported",
    knowledge_status="insufficient",
    web_status="error",
    user_id="v66-evt",
    thread_id="v66-t",
)
recent = read_log_file(400)
names = {e.get("event") for e in recent}
check(
    "10a. FALLBACK_START + FALLBACK_DECISION émis",
    "FALLBACK_START" in names and "FALLBACK_DECISION" in names,
    str(
        [
            n
            for n in names
            if n and n.startswith("FALLBACK")
        ]
    ),
)
# Champs requis §14 sur l'event DECISION
dec_events = [e for e in recent if e.get("event") == "FALLBACK_DECISION"]
if dec_events:
    e = dec_events[-1]
    # extra est mergé au top-level du record JSON (log_event §)
    check(
        "10b. FALLBACK_DECISION porte action/subject/routing_status/"
        "knowledge_status/web_status",
        all(
            k in e
            for k in (
                "action",
                "subject",
                "routing_status",
                "knowledge_status",
                "web_status",
            )
        ),
        str(sorted(e.keys()))[:130],
    )
else:
    check("10b. FALLBACK_DECISION champs", False, "aucun event")

# §7 : états JAMAIS convertis silencieusement
d = decide_fallback(
    "supported",
    knowledge_status="insufficient",
    web_status="error",
)
check(
    "11a. source_status préserve les états distincts",
    "supported" in d.source_status
    and "insufficient" in d.source_status
    and "error" in d.source_status,
    d.source_status,
)
check(
    "11b. raison explicite non générique ('not found' interdit)",
    d.reason
    and "not found" not in d.reason.lower()
    and len(d.reason) > 20,
    d.reason[:60],
)

# §8 : transparence — note pour le prompt LLM
d_web = decide_fallback(
    "supported",
    knowledge_status="insufficient",
    web_status="found",
    has_web_results=True,
)
note = fallback_note_for_prompt(d_web)
check(
    "12a. fallback web → note transparente (recherche web tentée)",
    "recherche web" in note.lower() or "RECHERCHE WEB" in note,
    note[:60],
)
note_gt = fallback_note_for_prompt(
    decide_fallback(
        "supported",
        knowledge_status="insufficient",
        web_status="unavailable",
    )
)
check(
    "12b. fallback general tutor → raison expliquée",
    "tuteur général" in note_gt.lower()
    or "général" in note_gt.lower(),
    note_gt[:60],
)
note_loc = fallback_note_for_prompt(
    decide_fallback("supported", knowledge_status="found")
)
check(
    "12c. local knowledge → pas de note fallback (pas un fallback)",
    note_loc == "",
)

# §10 : candidates pour clarification ambiguous
from app.services.context.builder import build_context  # noqa: E402

bc = build_context("v66-t", "v66-t", "Parle-moi des reseaux.")
check(
    "13. ambiguous réel → candidates transmises à la décision",
    bc.fallback.action == "ask_clarification"
    and "computer_networks" in bc.fallback.candidates
    and "neural_networks" in bc.fallback.candidates,
    str(bc.fallback.candidates),
)

# §12 : knowledge insufficient ≠ subject unsupported
d = decide_fallback(
    "supported",
    knowledge_status="insufficient",
    web_status="found",
    has_web_results=True,
)
check(
    "14. supported+insufficient tente le web (≠ unsupported)",
    d.action == "use_web_search"
    and d.source_status.startswith("supported"),
    f"{d.action} / {d.source_status}",
)

# §13 : web failure ne casse rien — builder complet survit
bc2 = build_context("v66-t", "v66-t", "python async asyncio")
check(
    "15. builder survive au pipeline web complet (no crash)",
    bc2.routing.status == "supported"
    and bc2.fallback.action in ("use_web_search",
                                "use_general_tutor"),
    bc2.fallback.action,
)

# Schéma : Literal action protégé
try:
    FallbackDecision(action="invented_action", reason="x")
    bad = False
except Exception:
    bad = True
check("16. FallbackDecision Literal action protégé", bad)

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
print("TESTS V6.6 FALLBACK: OK")
