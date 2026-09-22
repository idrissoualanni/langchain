# Tests PHASE 2 — Evaluation Engine (§18/§19/§20).
#
# Scope (déterministe, aucun LLM / aucun serveur / aucun réseau) :
#   A. Contrat EvaluationResult (§20) : extra=forbid, verdict Literal,
#      score/confidence bornés [0..1], constructeur make_evaluation.
#   B. Scoring textuel déterministe (text_scoring) : strip_accents,
#      key_terms (<= max_terms, mots techniques), content_tokens /
#      stopwords FR+EN, score_course_answer (covered/missing, score 0..1).
#   C. EvaluationEngine (§19/§20) : STRATEGY_ORDER, stratégie
#      deterministic en priorité, score None -> verdict unclear,
#      sizing 6/6, verdict mapping, evidence deterministic.
#   D. Séparation §18 : update_activity_with_result ADDITIF (jamais
#      status/attempts/last_evaluation), evaluation_to_result_dict.
#   E. Observations (§18) : result_to_observation (mapping/truncation 3),
#      emit_observation short-circuit user_id vide.
# Aucun appel à app.agent.graph.get_agent().
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


# ============================================================
# A. CONTRAT EVALUATIONRESULT (§20)
# ============================================================
from pydantic import ValidationError  # noqa: E402

from app.services.evaluation.schemas import (  # noqa: E402
    EvaluationResult,
    Verdict,
    make_evaluation,
)

r20 = EvaluationResult(activity_id="a-1")
check(
    "A: EvaluationResult defaults (score None, confidence 1.0, verdict partial)",
    r20.activity_id == "a-1"
    and r20.score is None
    and r20.confidence == 1.0
    and r20.verdict == "partial"
    and r20.weaknesses == []
    and r20.strategy == [],
    str(r20),
)

try:
    EvaluationResult(activity_id="x", bogus=1)
    check("A: extra=forbid rejette champ inconnu", False)
except ValidationError:
    check("A: extra=forbid rejette champ inconnu", True)

try:
    EvaluationResult(activity_id="x", verdict="invalide")
    check("A: verdict hors Literal rejete", False)
except ValidationError:
    check("A: verdict hors Literal rejete", True)

try:
    EvaluationResult(activity_id="x", score=1.5)
    check("A: score > 1.0 rejete", False)
except ValidationError:
    check("A: score > 1.0 rejete", True)

try:
    EvaluationResult(activity_id="x", score=-0.1)
    check("A: score < 0.0 rejete", False)
except ValidationError:
    check("A: score < 0.0 rejete", True)

try:
    EvaluationResult(activity_id="x", confidence=1.2)
    check("A: confidence > 1.0 rejete", False)
except ValidationError:
    check("A: confidence > 1.0 rejete", True)

check(
    "A: Verdict autorise les 6 valeurs du contrat",
    set(Verdict.__args__)
    == {"correct", "mostly_correct", "partial", "incorrect", "unclear", "error"},
    str(set(Verdict.__args__)),
)

me = make_evaluation(
    activity_id="a-2",
    score=0.8,
    verdict="correct",
    strengths=["x"],
    weaknesses=["y"],
    feedback="bien",
    evidence=[{"dimension": "deterministic"}],
    confidence=0.9,
)
check(
    "A: make_evaluation construit un EvaluationResult valide",
    isinstance(me, EvaluationResult)
    and me.score == 0.8
    and me.verdict == "correct"
    and me.strengths == ["x"]
    and me.weaknesses == ["y"]
    and me.confidence == 0.9,
)
check(
    "A: make_evaluation default strategy deterministic",
    make_evaluation(activity_id="a-3").strategy == ["deterministic"],
)

# ============================================================
# B. SCORING TEXTUEL DETERMINISTE (text_scoring)
# ============================================================
from app.services.evaluation.text_scoring import (  # noqa: E402
    EVAL_STOP_WORDS,
    content_tokens,
    key_terms,
    score_course_answer,
    strip_accents,
)

check(
    "B: strip_accents normalise ('fonctionne' vs 'fonctionné')",
    strip_accents("fonctionné") == "fonctionne"
    and strip_accents("fonction") == "fonction"
    and strip_accents("café") == "cafe",
)

check(
    "B: stopwords FR/EN exclus ('le','de','the','is')",
    "le" in EVAL_STOP_WORDS
    and "de" in EVAL_STOP_WORDS
    and "the" in EVAL_STOP_WORDS
    and "is" in EVAL_STOP_WORDS,
)

body = ("La fonction map applique une fonction a chaque element "
        "d une liste en Python")
kt = key_terms(body)
check(
    "B: key_terms <= max_terms (6)",
    len(kt) == 6,
    str(kt),
)
check(
    "B: key_terms prefere les mots techniques longs",
    kt[0] in ("fonction", "applique", "element", "chaque", "python")
    and "map" not in kt
    and not (set(kt) & EVAL_STOP_WORDS),
    str(kt),
)
check(
    "B: key_terms = termes attendus",
    kt == ["fonction", "applique", "element", "chaque", "python", "liste"],
    str(kt),
)

tok = content_tokens("Le chat is on the cours")
check(
    "B: content_tokens filtre stopwords FR/EN",
    tok == {"chat", "cours"},
    str(tok),
)

eng_content = "python function returns result"
s1, cov1, miss1 = score_course_answer(eng_content, "function returns")
check(
    "B: score_course_answer covered/missing et score 0..1",
    s1 == 0.5
    and cov1 == ["function", "returns"]
    and miss1 == ["python", "result"],
    f"score={s1} covered={cov1} missing={miss1}",
)

s2, cov2, miss2 = score_course_answer(eng_content, "")
check(
    "B: reponse vide -> score 0.0, covered vide, tout manquant",
    s2 == 0.0
    and cov2 == []
    and miss2 == ["function", "returns", "python", "result"],
    f"score={s2} covered={cov2} missing={miss2}",
)

s3, _, _ = score_course_answer(eng_content, "python function returns result")
check(
    "B: reponse parfaite -> score eleve >= 0.5",
    s3 >= 0.5,
    f"score={s3}",
)

s4, cov4, miss4 = score_course_answer("", "python function returns")
check(
    "B: reference vide + reponse -> score 0.0",
    s4 == 0.0 and cov4 == [] and miss4 == [],
    f"score={s4}",
)

s5, _, _ = score_course_answer(body, "la fonction Python calcule la liste")
check(
    "B: reponse francaise partielle -> score dans [0..1]",
    0.0 <= s5 <= 1.0,
    f"score={s5}",
)

# ============================================================
# C. EVALUATIONENGINE (§19/§20)
# ============================================================
from app.services.evaluation.engine import (  # noqa: E402
    ENGINE,
    EvaluationEngine,
    evaluate_activity,
)

check(
    "C: STRATEGY_ORDER exact (§19, deterministic en tete, llm dernier)",
    EvaluationEngine.STRATEGY_ORDER
    == ("deterministic", "execution", "domain_rules", "llm"),
    str(EvaluationEngine.STRATEGY_ORDER),
)

ref = body
er = ENGINE.evaluate(
    activity_id="a-10",
    activity_type="exercise",
    answer="La fonction map applique une fonction a chaque element de la liste",
    reference=ref,
)
check(
    "C: evaluate avec reference -> strategy deterministic + score calcule",
    er.strategy == ["deterministic"]
    and er.score is not None
    and 0.0 <= er.score <= 1.0,
    str(er.model_dump()),
)
check(
    "C: verdict correct si score >= 0.75",
    er.verdict == "correct",
    er.verdict,
)
check(
    "C: evidence = 1 entree dimension deterministic",
    len(er.evidence) == 1
    and er.evidence[0].get("dimension") == "deterministic",
    str(er.evidence),
)
check(
    "C: confidence par defaut = 0.9",
    er.confidence == 0.9,
    str(er.confidence),
)

ep = ENGINE.evaluate(
    activity_id="a-11",
    activity_type="exercise",
    answer="rien",
    score=0.5,
    covered=["a", "b", "c", "d", "e", "f", "g"],
    missing=["h", "i", "j", "k", "l", "m", "n"],
)
check(
    "C: score pre-calcule -> strategy deterministic, verdict partial",
    ep.strategy == ["deterministic"]
    and ep.score == 0.5
    and ep.verdict == "partial",
    str(ep.model_dump()),
)
check(
    "C: strengths/weaknesses tronques a 6",
    len(ep.strengths) == 6
    and len(ep.weaknesses) == 6
    and ep.strengths == ["a", "b", "c", "d", "e", "f"]
    and ep.weaknesses == ["h", "i", "j", "k", "l", "m"],
    f"strengths={ep.strengths} weaknesses={ep.weaknesses}",
)

eu = ENGINE.evaluate(
    activity_id="a-12", activity_type="exercise", answer="sans cours"
)
check(
    "C: sans reference ni score -> score None, verdict unclear",
    eu.score is None and eu.verdict == "unclear" and eu.evidence == [],
    str(eu.model_dump()),
)

check(
    "C: verdict incorrect si score < 0.4",
    ENGINE.evaluate(activity_id="a-13", activity_type="exercise",
                    answer="x", score=0.2).verdict == "incorrect",
)
check(
    "C: verdict correct si score >= 0.75, partial sinon",
    ENGINE.evaluate(activity_id="a-14", activity_type="exercise",
                    answer="x", score=0.8).verdict == "correct",
)

ea = evaluate_activity(
    activity_id="a-15",
    activity_type="quiz",
    answer="function returns",
    reference=eng_content,
)
check(
    "C: evaluate_activity API publique -> meme moteur",
    isinstance(ea, EvaluationResult)
    and ea.strategy == ["deterministic"]
    and ea.score == 0.5,
    str(ea.model_dump()),
)

# ============================================================
# D. SEPARATION §18 : UPDATE ACTIVITY ADDITIF
# ============================================================
from app.services.evaluation.engine import (  # noqa: E402
    evaluation_to_result_dict,
    update_activity_with_result,
)

rd = evaluation_to_result_dict(er)
check(
    "D: evaluation_to_result_dict 7 cles §20",
    set(rd.keys())
    == {"score", "verdict", "strengths", "weaknesses", "feedback",
        "evidence", "confidence"},
    str(sorted(rd.keys())),
)

sample = {
    "status": "completed",
    "attempts": 4,
    "last_evaluation": {"old": True},
    "titre": "exercice 1",
}
snapshot = dict(sample)
updated = update_activity_with_result(sample, er)
check(
    "D: update_activity_with_result ADDITIF -> status/attempts/last untouched",
    sample["status"] == snapshot["status"]
    and sample["attempts"] == snapshot["attempts"]
    and sample["last_evaluation"] == snapshot["last_evaluation"],
    str(sample),
)
check(
    "D: seule cle 'result' ajoutee",
    set(sample.keys()) - set(snapshot.keys()) == {"result"},
    str(sorted(set(sample.keys()) - set(snapshot.keys()))),
)
check(
    "D: result dict aligne EvaluationResult",
    isinstance(sample["result"], dict)
    and sample["result"]["score"] == er.score
    and sample["result"]["verdict"] == er.verdict
    and sample["result"]["evidence"] == er.evidence
    and sample["result"]["feedback"] == er.feedback,
    str(sample["result"]),
)

nresult = update_activity_with_result("pas un dict", er)
check(
    "D: update_activity_with_result ignore non-dict",
    nresult == "pas un dict",
)

# ============================================================
# E. OBSERVATIONS (§18)
# ============================================================
from app.services.evaluation.observations import (  # noqa: E402
    emit_observation,
    result_to_observation,
)

obs = result_to_observation(
    ep, subject="mathematiques", topic="fonctions"
)
check(
    "E: result_to_observation mapping LearningObservation",
    obs == {
        "subject": "mathematiques",
        "topic": "fonctions",
        "type": "exercise",
        "score": 0.5,
        "strengths": ["a", "b", "c"],
        "weak_points": ["h", "i", "j"],
        "confidence": 0.8,
    },
    str(obs),
)

obs9 = result_to_observation(
    er, subject="python", topic="map",
    observation_type="quiz", confidence=0.7,
)
check(
    "E: observation type/confidence parametrables, truncation 3",
    obs9["type"] == "quiz"
    and obs9["confidence"] == 0.7
    and len(obs9["strengths"]) <= 3
    and obs9["strengths"] == er.strengths[:3],
    str(obs9),
)
check(
    "E: emit_observation short-circuit user_id vide",
    emit_observation(
        user_id="", thread_id="t-1", result=er,
        subject="python", topic="map", observation_type="exercise",
    ) is False,
)

# ============================================================
# Résumé
# ============================================================
print()
print(f"TOTAL: {PASS} | PASS: {PASS} | FAIL: {FAIL}")
print("TESTS PHASE 2 EVALUATION: OK" if FAIL == 0 else "TESTS PHASE 2 EVALUATION: ECHEC")
sys.exit(0 if FAIL == 0 else 1)