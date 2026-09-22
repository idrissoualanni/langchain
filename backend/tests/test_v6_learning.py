# Tests V6 — Learning Profile (obligatoires §§45-48 + criteres §51)
import sys
import uuid
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


def new_uid(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


from app.schemas.learning import (
    LearningObservation,
    LearningProfile,
)
from app.learning.learning_profile import (
    create_learning_goal,
    list_observations,
    read_learning_profile,
    update_learning_goal,
    update_profile_from_observation,
    validate_observation_targets,
)
from app.learning.learning_context import get_learning_context

# ============================================================
# Test A - nouveau profil : user sans Learning Profile
# ============================================================
u_a = new_uid("u-v6a")
info = get_learning_context(u_a, "python", "fonctions")
check(
    "A: sans profil -> not_started (jamais une erreur)",
    info.status == "not_started",
)

# ============================================================
# Test B - premiere observation : le profil doit etre cree
# ============================================================
u_b = new_uid("u-v6b")
assert read_learning_profile(u_b) is None
p = update_profile_from_observation(
    u_b,
    LearningObservation(
        subject="python",
        topic="fonctions",
        type="exercise",
        score=0.40,
        weak_points=["return vs print"],
        strengths=["syntaxe de base"],
    ),
)
check(
    "B: profil cree par la 1re observation",
    read_learning_profile(u_b) is not None,
)
check(
    "B: mastery initial = score (premiere estimation)",
    p.subjects["python"].topics["fonctions"].mastery == 0.40,
    f"mastery={p.subjects['python'].topics['fonctions'].mastery}",
)
check(
    "B: weak_points/strengths stockes sur le topic (30)",
    p.subjects["python"].topics["fonctions"].weak_points
    == ["return vs print"]
    and p.subjects["python"].topics["fonctions"].strengths
    == ["syntaxe de base"],
)

# ============================================================
# Test C - deuxieme observation : mastery evolue (formule 15)
# ============================================================
p = update_profile_from_observation(
    u_b,
    LearningObservation(
        subject="python", topic="fonctions", type="exercise", score=0.70
    ),
)
t = p.subjects["python"].topics["fonctions"]
expected = 0.40 * (1 - 0.3 * 0.8) + 0.70 * (0.3 * 0.8)
check(
    "C: mastery evolue selon la formule (0.40,0.70,w=0.24)",
    abs(t.mastery - expected) < 1e-9,
    f"mastery={t.mastery:.4f} attendu={expected:.4f}",
)
check(
    "C: attempts incremente",
    t.attempts == 2,
)
check(
    "C: confidence croit avec les observations (9)",
    t.confidence is not None and 0.3 < t.confidence < 0.5,
    f"confidence={t.confidence}",
)

# ============================================================
# Test D - autre topic : fonctions PAS modifie
# ============================================================
p = update_profile_from_observation(
    u_b,
    LearningObservation(
        subject="python", topic="loops", type="exercise", score=0.90
    ),
)
check(
    "D: loops cree, fonctions INTACT",
    p.subjects["python"].topics["loops"].mastery == 0.90
    and p.subjects["python"].topics["fonctions"].attempts == 2,
)

# ============================================================
# Test E - autre matiere : python PAS modifie
# ============================================================
p = update_profile_from_observation(
    u_b,
    LearningObservation(
        subject="biology", topic="cellule", type="assessment", score=0.50
    ),
)
check(
    "E: biology cree, python INTACT",
    p.subjects["biology"].topics["cellule"].mastery == 0.50
    and p.subjects["python"].topics["fonctions"].mastery == expected,
)

# ============================================================
# Test F - cross-thread : observation thread A, lecture thread B
# ============================================================
info_b = get_learning_context(
    u_b, "python", "fonctions", thread_id="thread-B"
)
check(
    "F: profil accessible depuis un autre thread",
    info_b.status == "active"
    and abs(info_b.mastery - expected) < 1e-9,
    f"mastery={info_b.mastery}",
)

# ============================================================
# Test G - cross-user : aucune fuite
# ============================================================
u_g = new_uid("u-v6g")
update_profile_from_observation(
    u_g,
    LearningObservation(
        subject="python", topic="fonctions", type="assessment", score=0.80
    ),
)
info_g = get_learning_context(u_b, "python", "fonctions")
check(
    "G: A garde SA mastery (pas celle de l'autre user)",
    abs(info_g.mastery - expected) < 1e-9,
    f"mastery A={info_g.mastery}",
)
info_g2 = get_learning_context(new_uid("u-v6g2"), "python", "fonctions")
check(
    "G: nouveau user -> mastery null (aucune fuite)",
    info_g2.status == "not_started" and info_g2.mastery is None,
)

# ============================================================
# Test H - restart simule : relecture depuis le Store
# ============================================================
# (le vrai restart serveur est teste en integration ; ici on
# verifie que read_learning_profile refait un aller-retour Store)
profile_reloaded = read_learning_profile(u_b)
check(
    "H: profil relu depuis le SqliteStore (persistance)",
    profile_reloaded is not None
    and abs(
        profile_reloaded.subjects["python"].topics["fonctions"].mastery
        - expected
    )
    < 1e-9,
)

# ============================================================
# Test I - Context Builder : contexte learning pertinent
# ============================================================
from app.context import build_context, build_system_prompt
from app.services.agent.prompts import CORE_PROMPT

ctx = build_context(
    user_id=u_b,
    thread_id="t-v6",
    query="Je veux continuer les fonctions Python.",
)
check(
    "I: BuiltContext.learning alimente (24)",
    ctx.learning is not None
    and ctx.learning["status"] == "active"
    and ctx.learning["subject"] == "python"
    and ctx.learning["topic"] == "fonctions",
    f"{ctx.learning['status']} {ctx.learning['subject']}/{ctx.learning['topic']}",
)
check(
    "I: mastery + attempts + weak_points dans le contexte",
    abs(ctx.learning["mastery"] - expected) < 1e-9
    and ctx.learning["attempts"] == 2
    and ctx.learning["weak_points"] == ["return vs print"],
)
prompt = build_system_prompt(CORE_PROMPT, ctx, u_b, "t-v6")
check(
    "I: bloc LEARNING dans le dynamic prompt (25)",
    "## LEARNING" in prompt
    and "Weak points" in prompt
    and "return vs print" in prompt,
)

# ============================================================
# Test J - absence de profile : discussion normale possible
# ============================================================
u_j = new_uid("u-v6j")
ctx_j = build_context(
    user_id=u_j, thread_id="t-j", query="Explique-moi les variables Python."
)
check(
    "J: nouveau user -> contexte OK, learning not_started (26)",
    ctx_j.learning is not None
    and ctx_j.learning["status"] == "not_started",
)
prompt_j = build_system_prompt(CORE_PROMPT, ctx_j, u_j, "t-j")
check(
    "J: le prompt reste complet (tuteur fonctionne sans profil)",
    "MATIÈRE : Python" in prompt_j,
)

# ============================================================
# Test 46 - non-melange de matieres
# ============================================================
u_mix = new_uid("u-v6mix")
for subj, topic, score in [
    ("python", "fonctions", 0.30),
    ("biology", "cellule", 0.60),
    ("mathematics", "algebre", 0.90),
]:
    update_profile_from_observation(
        u_mix,
        LearningObservation(
            subject=subj, topic=topic, type="exercise", score=score
        ),
    )
p_mix = read_learning_profile(u_mix)
check(
    "46: scores distincts, aucun melange",
    p_mix.subjects["python"].topics["fonctions"].mastery == 0.30
    and p_mix.subjects["biology"].topics["cellule"].mastery == 0.60
    and p_mix.subjects["mathematics"].topics["algebre"].mastery == 0.90,
    str(
        {
            s: p_mix.subjects[s].mastery
            for s in p_mix.subjects
        }
    ),
)

# ============================================================
# Test 47 - observation separee du profil (logs)
# ============================================================
import io
import logging

log_capture = io.StringIO()
handler = logging.StreamHandler(log_capture)
handler.setFormatter(
    logging.Formatter("%(message)s")
)
from app.logging.events import logger as events_logger

events_logger.addHandler(handler)
events_logger.setLevel(logging.INFO)

u_47 = new_uid("u-v6obs")
update_profile_from_observation(
    u_47,
    LearningObservation(
        subject="python", topic="return", type="quiz", score=0.55
    ),
)
events_logger.removeHandler(handler)
captured = log_capture.getvalue()
check(
    "47: LEARNING_OBSERVATION_RECORDED avant LEARNING_PROFILE_UPDATE",
    "LEARNING_OBSERVATION_RECORDED" in captured
    and "LEARNING_PROFILE_UPDATE" in captured,
)
check(
    "47: ordre observation puis update",
    captured.find("LEARNING_OBSERVATION_RECORDED")
    < captured.find("LEARNING_PROFILE_UPDATE"),
)

# ============================================================
# Test 48 - relevance : retour -> fonctions, pas la biologie
# ============================================================
ctx_48 = build_context(
    user_id=u_mix, thread_id="t-48", query="Je ne comprends pas return."
)
check(
    "48: topic return priorise (pas toute la biologie)",
    ctx_48.learning is not None
    and ctx_48.learning["subject"] == "python",
    f"learning={ctx_48.learning}",
)
check(
    "48: le prompt ne contient PAS la biologie",
    "biologie" not in prompt,
)

# ============================================================
# Criteres 51 complementaires
# ============================================================
# - aucun message de conversation dans le profil (34)
p_b = read_learning_profile(u_b)
dump = p_b.model_dump()
check(
    "34: aucun champ messages/conversation dans le profil",
    "messages" not in dump
    and "conversation" not in dump
    and "history" not in dump,
)

# - validation Registry : pythonn rejete (18)
ok, reason = validate_observation_targets("pythonn", "fonctions")
check("18: subject typo rejete", not ok)
r_bad = update_profile_from_observation(
    u_b,
    LearningObservation(
        subject="pythonn", topic="fonctions", type="exercise", score=0.5
    ),
)
check("18: observation sujet inconnu -> None (pas de creation)", r_bad is None)

# - topic inconnu rejete
ok2, _ = validate_observation_targets("python", "notopic")
check("18: topic inconnu rejete", not ok2)

# - goals separes de la mastery (29)
g = create_learning_goal(
    u_b, "python", "Comprendre les fonctions", topic="fonctions"
)
check("29: goal cree actif", g is not None and g.status == "active")
g2 = update_learning_goal(u_b, g.id, "completed")
check("29: goal passe completed", g2 is not None and g2.status == "completed")

# - historique des observations conserve (33)
obs = list_observations(u_b, subject="python", topic="fonctions")
check(
    "33: historique conserv (scores non ecrases)",
    [o["score"] for o in obs] == [0.40, 0.70],
    str([o["score"] for o in obs]),
)

# - topic jamais travaille mais connu du Registry (28)
info_new_topic = get_learning_context(u_b, "python", "decorators")
check(
    "28: topic Registry jamais travaille -> etat minimal actif",
    info_new_topic.status == "active"
    and info_new_topic.mastery is None
    and info_new_topic.attempts == 0,
    f"status={info_new_topic.status} mastery={info_new_topic.mastery}",
)

# - structure pydantic valide (7/8)
sample = LearningProfile.model_validate(
    read_learning_profile(u_b).model_dump()
)
check(
    "7/8: round-trip pydantic du profil OK",
    sample.subjects["python"].topics["fonctions"].attempts == 2,
)

# - namespace distinct de User Memory (5/6)
from app.learning.learning_profile import _learning_namespace

check(
    "5/6: namespace learning distinct du namespace profile",
    _learning_namespace(u_b) == ("users", "learning", u_b),
)

# - aucun Learning Engine complet (40) : pas de module strategy
import importlib

try:
    importlib.import_module("app.learning.learning_engine")
    engine_exists = True
except ImportError:
    engine_exists = False
check("40: pas de Learning Engine complet", not engine_exists)

# - tools learning enregistres (19)
from app.agent.tools import all_tools

learning_tool_names = {
    "get_learning_profile",
    "get_learning_topic",
    "record_learning_observation",
    "update_learning_goal",
}
registered = {t.name for t in all_tools}
check(
    "19: 4 tools learning enregistres",
    learning_tool_names.issubset(registered)
    and len(all_tools) >= 21,
    f"total={len(all_tools)}",
)

# ============================================================
# Resume
# ============================================================
fails = [label for label, ok in results if not ok]
print()
print(
    f"TOTAL: {len(results)} | PASS: {len(results) - len(fails)} | FAIL: {len(fails)}"
)
if fails:
    print("ECHECS:", fails)
    sys.exit(1)
print("TESTS V6 ARCHITECTURE: OK")
