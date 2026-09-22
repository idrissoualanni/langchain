# Tests V5 â€” mÃ©canismes natifs LangChain + architecture (Â§Â§45-56)
import sys

sys.path.insert(0, ".")

results = []


def check(label, cond, detail=""):
    results.append((label, bool(cond)))
    print(
        f"[{'PASS' if cond else 'FAIL'}] {label}"
        + (f" -- {detail}" if detail else "")
    )


# ============================================================
# Â§54 â€” ROUTING STRUCTURÃ‰ (RoutingResult pydantic validÃ©)
# ============================================================
from app.context.router import route_subject
from app.schemas.context import RoutingResult

r = route_subject("Explique-moi les fonctions Python.")
check(
    "S54: RoutingResult pydantic validÃ©",
    isinstance(r, RoutingResult)
    and r.status == "supported"
    and r.subject == "python"
    and r.topic == "fonctions",
    f"{r.status}/{r.subject}/{r.topic}",
)
check(
    "S54: validation stricte (confidence bornÃ©e)",
    0.0 <= r.confidence <= 1.0,
)
try:
    RoutingResult(status="invalide")
    ok = False
except Exception:
    ok = True
check("S54: Literal status rejetÃ© si invalide", ok)

# Ambiguïté (§51) — « reseaux neurones » : réellement ambigu entre
# computer_networks et intelligence_artificielle (neural_networks
# n'est plus un sujet configuré depuis la V7 — topic de l'IA).
r = route_subject("Parle-moi des reseaux neurones.")
check(
    "S51: ambiguous + candidates",
    r.status == "ambiguous"
    and set(r.candidates) == {
        "computer_networks",
        "intelligence_artificielle",
    },
    f"{r.status}/{r.candidates}",
)

# Unsupported (Â§50)
r = route_subject("Explique-moi l astrophysique.")
check(
    "S50: unsupported â†’ General Tutor",
    r.status == "unsupported" and r.subject == "astrophysique",
)

# Unknown (Â§17)
r = route_subject("Quel temps fait-il demain ?")
check("S17: unknown, pas de subject inventÃ©", r.status == "unknown" and r.subject is None)

# ============================================================
# Â§49 â€” TEST AJOUT DE MATIÃˆRE (registry dÃ©couvre, moteur intact)
# ============================================================
import shutil
from pathlib import Path

DEF_DIR = Path("app/subjects/definitions")
KN_DIR = Path("app/knowledge")

# Sauvegarde pour restauration
astro_yaml = DEF_DIR / "astronomy.yaml"
astro_kn = KN_DIR / "sciences" / "astronomie" / "star_life.md"

# Capture de l'original AVANT mutation (restauré en fin de test).
orig_yaml = astro_yaml.read_text(encoding="utf-8") if astro_yaml.exists() else None
orig_kn = astro_kn.read_text(encoding="utf-8") if astro_kn.exists() else None

astro_yaml.write_text(
    """id: astronomy
name: Astronomie
domain: sciences
description: >
  Science des astres et du cosmos.
teaching_style:
  - visuel
pedagogical_guidelines:
  - utiliser des analogies d echelle
capabilities:
  - explain
  - quiz
tools:
  common:
    - create_exercise
    - evaluate_answer
    - give_hint
  specialized: []
knowledge:
  sources:
    - sciences/astronomie/star_life
topics:
  - etoiles
  - planetes
  - cosmos
aliases:
  - astronomie
model:
  provider: ollama
  name: qwen2.5
""",
    encoding="utf-8",
)
astro_kn.parent.mkdir(parents=True, exist_ok=True)
astro_kn.write_text(
    "# Astronomie â€” Vie des Ã©toiles\n\n"
    "## etoiles\n"
    "Une Ã©toile est une boule de plasma tenant en Ã©quilibre "
    "entre sa gravitÃ© et la pression de fusion nuclÃ©aire de son "
    "cÅ“ur. L'Ã©nergie rayonnÃ©e provient de la fusion de l'hydrogÃ¨ne "
    "en hÃ©lium.\n",
    encoding="utf-8",
)

# Invalider le cache registry pour dÃ©couvrir astronomy
from app.subjects import registry as reg

reg.invalidate()
reloaded = reg.load_registry()
check(
    "S49: astronomy dÃ©couverte via registry (sans modifier moteur)",
    "astronomy" in reloaded,
    str(sorted(reloaded.keys())),
)

# Router la dÃ©couvre immÃ©diatement (alias astronomie)
r = route_subject("Explique-moi l astronomie et les etoiles.")
check(
    "S49: routing astronomy supported + topic etoiles",
    r.status == "supported"
    and r.subject == "astronomy"
    and r.topic == "etoiles",
    f"{r.status}/{r.subject}/{r.topic}",
)

# Knowledge retriever la trouve aussi
from app.context.knowledge_retriever import search_knowledge

k = search_knowledge("astronomy", "etoiles", "la vie des etoiles")
check(
    "S49: knowledge astronomy trouvÃ©",
    k["status"] == "found" and len(k["items"]) >= 1,
    f"{k['status']}",
)

# builder/graph/runner/middleware NON modifiÃ©s â€” vÃ©rifiÃ©s par
# le fait qu'on n'a touchÃ© Ã  aucun fichier moteur.

# §52 — knowledge absent : matière valide SANS source knowledge
# (« geographie » est configurée depuis la V6.5 dans
# sciences_humaines_communication → remplacée par javascript,
# toujours taxonomy-only → unsupported)
r = route_subject("Explique-moi le javascript.")  # taxonomy: javascript
check(
    "S52: unsupported → pas de faux knowledge",
    r.status == "unsupported",
)

# ============================================================
# Â§53 â€” TOOL INEXISTANT (declared mais non enregistrÃ©)
# ============================================================
from app.subjects.tool_registry import resolve_tools

available, unavailable = resolve_tools(
    ["create_exercise", "execute_python", "give_hint"]
)
check(
    "S53: execute_python dÃ©tectÃ© unavailable",
    "execute_python" in unavailable
    and "execute_python" not in available,
    f"available={available} | unavailable={unavailable}",
)
check(
    "S53: tools rÃ©els dans available",
    "create_exercise" in available and "give_hint" in available,
)

# ============================================================
# Â§30 â€” BUILT CONTEXT STRUCTURÃ‰
# ============================================================
from app.context import build_context
from app.schemas.context import BuiltContext

import uuid

# user de test avec faits Â§45
from app.agent.memory import get_store, save_fact

TEST_USER = "u-v5-" + uuid.uuid4().hex[:8]
# note: pas un UUID valide pour le store ? le store accepte str.
for cat, content in [
    ("interest", "S interesse a la robotique et construit des drones"),
    ("interest", "Passionne par l aeronautique depuis l enfance"),
    ("interest", "Etudie la mecatronique a l universite"),
    ("preference", "Prefere les explications avec des exemples concrets"),
]:
    save_fact(TEST_USER, category=cat, content=content)

ctx = build_context(
    user_id=TEST_USER,
    thread_id="t-v5",
    query="Explique-moi return en Python.",
)
check(
    "S30: BuiltContext pydantic",
    isinstance(ctx, BuiltContext),
)
check(
    "S45: intÃ©rÃªts non pertinents absents (robotique/aÃ©ro/mÃ©ca)",
    "robotique" not in ctx.user.text.lower()
    and "aeronautique" not in ctx.user.text.lower()
    and "mecatronique" not in ctx.user.text.lower(),
    f"user_chars={len(ctx.user.text)}",
)
check(
    "S45: knowledge return trouvÃ©",
    ctx.knowledge.status == "found"
    and any(i.topic == "return" for i in ctx.knowledge.items),
    ctx.knowledge.status,
)
check(
    "S45: tools rÃ©solus (3 pÃ©dagogiques available)",
    "create_exercise" in ctx.tools.available,
)
check(
    "S30: stats budget prÃ©sentes",
    ctx.stats.memories_used >= 0
    and ctx.stats.knowledge_items >= 1,
)

# Â§48 â€” pas de mÃ©lange de configs
ctx_bio = build_context(
    user_id=TEST_USER,
    thread_id="t-v5",
    query="Explique-moi la membrane cellulaire.",
)
check(
    "S48: biologie â‰  python (configs non mÃ©langÃ©es)",
    ctx_bio.subject is not None
    and ctx_bio.subject.id == "biology"
    and ctx.subject.id == "python",
    f"{ctx.subject.id} vs {ctx_bio.subject.id}",
)

# ============================================================
# ============================================================
# §56 — FALLBACK CONTEXT BUILDER (erreur → Core Prompt)
# On teste via wrap_model_call du middleware dynamic_prompt (API
# réelle du décorateur) avec un handler noop.
# ============================================================
from app.agent.middleware import tutor_dynamic_prompt
from langchain.agents.middleware import ModelRequest
from langchain_core.messages import HumanMessage


def _make_request(user_id: str | None = None, thread_id: str = "t-v5"):
    """Construit un VRAI ModelRequest (avec .override) + runtime
    AgentContext — l'API réelle du dynamic_prompt."""
    from langchain_ollama import ChatOllama

    from app.schemas.context import AgentContext

    context = (
        AgentContext(user_id=user_id, thread_id=thread_id)
        if user_id
        else None
    )

    class _CtxRuntime:
        def __init__(self, ctx):
            self.context = ctx
            self.store = None

    return ModelRequest(
        model=ChatOllama(model="x"),
        messages=[
            HumanMessage(
                content="Explique-moi return en Python."
            )
        ],
        system_prompt=None,
        runtime=_CtxRuntime(context),
    )


def _capture_handler(request):
    """Handler noop : capture le system_message réellement envoyé."""
    _capture_handler.last_prompt = (
        request.system_message.content
        if request.system_message is not None
        else None
    )
    return "ok"


_capture_handler.last_prompt = None

from app.agent.prompts import CORE_PROMPT

# Cas 1 : sans user_id dans le runtime → CORE_PROMPT seul
req_nouser = _make_request(user_id=None)
tutor_dynamic_prompt.wrap_model_call(
    req_nouser, _capture_handler
)
p_nouser = _capture_handler.last_prompt
check(
    "S56: sans user_id -> CORE_PROMPT seul",
    p_nouser is not None and p_nouser.strip() == CORE_PROMPT.strip(),
)

# Cas 2 : erreur du builder → CONTEXT_BUILD_ERROR → CORE_PROMPT
import app.context as ctx_pkg

_orig_pkg_build = ctx_pkg.build_context


def _boom(*a, **k):
    raise RuntimeError("simulated context failure")


ctx_pkg.build_context = _boom
req_user = _make_request(user_id=TEST_USER)
tutor_dynamic_prompt.wrap_model_call(
    req_user, _capture_handler
)
p_err = _capture_handler.last_prompt
ctx_pkg.build_context = _orig_pkg_build
check(
    "S56: erreur builder -> CORE_PROMPT (pas de crash)",
    p_err is not None and p_err.strip() == CORE_PROMPT.strip(),
)

# Cas 3 : nominal → prompt dynamique complet (§55)
tutor_dynamic_prompt.wrap_model_call(
    req_user, _capture_handler
)
p_ok = _capture_handler.last_prompt
check(
    "S55: dynamic prompt natif construit (MATIERE + USER CONTEXT)",
    p_ok is not None
    and "MATIÈRE : Python" in p_ok
    and "USER CONTEXT" in p_ok
    and p_ok.strip() != CORE_PROMPT.strip(),
    f"{len(p_ok)} chars",
)
check(
    "S36: pas d'ID techniques dans le prompt",
    TEST_USER not in (p_ok or "") and "user_id=" not in (p_ok or ""),
)

# ============================================================
# Â§4 â€” RUNTIME CONTEXT (AgentContext transportÃ© par context=)
# ============================================================
from app.schemas.context import AgentContext

ac = AgentContext(user_id="u1", thread_id="t1")
check(
    "S4: AgentContext (dataclass runtime DI)",
    ac.user_id == "u1" and ac.thread_id == "t1",
)

# graph.py expose context_schema=AgentContext — dans _build_agent
# (get_agent est un simple cache qui délègue ; la vraie confection
# est le facteur commun _build_agent, graph.py:105)
import inspect

import app.agent.graph as graph_mod

src = inspect.getsource(graph_mod._build_agent)
check(
    "S4: graph.py passe context_schema=AgentContext",
    "context_schema=AgentContext" in src,
)
# runner.py passe context= Ã  invoke
import app.agent.runner as runner_mod

rsrc = inspect.getsource(runner_mod)
check(
    "S4: runner passe context=AgentContext Ã  invoke",
    "context=context" in rsrc or "context=AgentContext" in rsrc,
)

# ============================================================
# Â§46 â€” CROSS-THREAD (mÃ©moire user visible, threads sÃ©parÃ©s)
# ============================================================
ctx_t1 = build_context(
    user_id=TEST_USER, thread_id="thread-A1", query="mes preferences ?"
)
ctx_t2 = build_context(
    user_id=TEST_USER, thread_id="thread-A2", query="mes preferences ?"
)
check(
    "S46: mÃ©moire user accessible cross-thread (A1â†’A2)",
    len(ctx_t1.user.text) > 0
    and ctx_t1.user.text == ctx_t2.user.text
    and ctx_t1.thread.thread_id != ctx_t2.thread.thread_id,
)

# ============================================================
# Â§47 â€” ISOLATION UTILISATEURS
# ============================================================
USER_B = "u-v5b-" + uuid.uuid4().hex[:8]
save_fact(USER_B, category="identity", content="S appelle Bruno")

ctx_a = build_context(
    user_id=TEST_USER, thread_id="t", query="explique python"
)
ctx_b = build_context(
    user_id=USER_B, thread_id="t", query="explique python"
)
check(
    "S47: mÃ©moire de B ne contient pas celle de A",
    "robotique" not in ctx_b.user.text
    and "mecatronique" not in ctx_b.user.text,
)
check(
    "S47: B a sa propre mÃ©moire",
    "Bruno" in ctx_b.user.text or ctx_b.user.text != ctx_a.user.text,
)

# ============================================================
# Â§55 â€” DYNAMIC PROMPT (changement mÃ©moire visible au prochain appel)
# ============================================================
from app.context import build_system_prompt
from app.agent.prompts import CORE_PROMPT

p1 = build_system_prompt(CORE_PROMPT, ctx_a, TEST_USER, "t")
save_fact(TEST_USER, category="preference", content="Aime les schema colores")
ctx_a2 = build_context(
    user_id=TEST_USER, thread_id="t", query="mes preferences ?"
)
p2 = build_system_prompt(CORE_PROMPT, ctx_a2, TEST_USER, "t")
check(
    "S55: nouveau MemoryFact visible au prochain appel",
    len(p2) != len(p1) or p1 != p2,
    f"{len(p1)} -> {len(p2)} chars",
)
check(
    "S36: pas d'ID techniques dans le prompt",
    TEST_USER not in p1 and "user_id=" not in p1,
)

# ============================================================
# RÃ©sumÃ©
# ============================================================
fails = [label for label, ok in results if not ok]
print()
print(
    f"TOTAL: {len(results)} | PASS: {len(results) - len(fails)} | FAIL: {len(fails)}"
)
if fails:
    print("ECHECS:", fails)

# Nettoyage astronomy (matiÃ¨re de test Â§49)
# Restauration astronomy (matiere de test S49) : restaurer l'original,
# ne jamais detruire un fichier tracke.
if orig_yaml is None:
    astro_yaml.unlink(missing_ok=True)
else:
    astro_yaml.write_text(orig_yaml, encoding="utf-8")
if orig_kn is None:
    shutil.rmtree(astro_kn.parent, ignore_errors=True)
else:
    astro_kn.parent.mkdir(parents=True, exist_ok=True)
    astro_kn.write_text(orig_kn, encoding="utf-8")
reg.invalidate()
print("cleanup astronomy ok")
if fails:
    sys.exit(1)

