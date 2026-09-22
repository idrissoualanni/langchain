# Problem Subgraph — ÉVALUATION d'étape + erreurs classifiées (§21).
#
# evaluate_step : évalue UNE soumission d'étape via le moteur
# d'évaluation §20 (EvaluationEngine) — même formule de scoring
# canonique que partout (text_scoring), PAS une seconde évaluation
# (§18 : une seule évaluation). En complément, une classification
# DÉTERMINISTE d'erreur rapproche la soumission de l'attendu pour
# produire le champ error_kind (§21 : unite/formule/signe/methode).
#
# classify_error_kind : règles lexicales pures (unités, signe -,
# formulation) — n'exécute jamais de résolution.
from __future__ import annotations

import re

from app.evaluation.engine import ENGINE
from app.schemas.problem import (
    ErrorKind,
    SolutionStep,
    StepEvaluation,
)

# Marqueurs d'erreur par catégorie.
_UNIT_TOKEN_RE = re.compile(r"\b(m|s|kg|mol|a|c|km|cm|mm|degre|degres|h|min|l|g|t|eur)\b", re.IGNORECASE)

# Parenthèses mal équilibrées → "methode" (structure de calcul).
_BALANCE_RE = re.compile(r"[()\[\]]")

# Normalisation générique appliquée aux entités mathématiques avant
# comparaison lexicographique (espaces, accents, symboles Unicode).
_MATH_NORM = [
    (r"\s+", ""),
    (r"[,;]", "."),
    (r"×", "*"),
    (r"÷", "/"),
    (r"−", "-"),
    (r"—", "-"),
    (r"–", "-"),
    (r"’", "'"),
    ("", ""),
]


def _norm_math(text: str) -> str:
    """Normalise une entité mathématique pour comparaison (§21)."""
    out = text or ""
    for pat, repl in _MATH_NORM[:-1]:
        out = re.sub(pat, repl, out)
    out = out.replace(" ", "").strip().lower()
    return out


def _math_exact_score(submission: str, reference: str) -> float | None:
    """Score déterministe d'une égalité mathématique exacte après
    normalisation. Retourne None si la référence ne ressemble pas à une
    expression mathématique (auquel cas le moteur §20 — textuel — reste
    l'autorité). Score 1.0 si égalité, 0.0 sinon."""
    ref = _norm_math(reference or "")
    if not ref or not re.search(r"[\d=+\-*/^x]", ref):
        return None
    sub = _norm_math(submission or "")
    return 1.0 if (sub and sub == ref) else 0.0


def _error_balance(text: str) -> bool:
    """Vérifie l'équilibre des parenthèses — erreur de méthode."""
    depth = 0
    for ch in text or "":
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
            if depth < 0:
                return True
    return depth != 0


def classify_error_kind(submission: str, expected: str, reference: str = "") -> ErrorKind:
    """Classifie DÉTERMINISTE l'erreur d'une soumission (§21).

    Ordre :
      1. "unite"   — unité attendue mais différente dans la soumission
      2. "signe"   — un signe négatif attendu est absent (ou inversé)
      3. "formule" — l'expression attendue/reference diffère fortement
      4. "methode" — syntaxe/équilibre parenthèses ou trop éloigné
      5. "aucune"  — ne pas trancher (une pièce de plus n'est pas une
                     erreur classée : la décision revient au moteur §20)
    """
    sub = (submission or "").strip().lower()
    exp = (expected or "").strip().lower()
    ref = (reference or "").strip().lower()

    if not sub:
        return "aucune"

    # 1. Unité attendue mais incompatibles.
    exp_units = set(_UNIT_TOKEN_RE.findall(exp))
    sub_units = set(_UNIT_TOKEN_RE.findall(sub))
    if exp_units and exp_units != sub_units:
        return "unite"

    # 2. Signe négatif attendu (dans expected/reference) absent.
    neg_expected = "-" in exp or "-" in ref
    if neg_expected and "-" not in sub:
        return "signe"

    # 3. Formule : reference contient des tokens distincts de la soumission.
    if ref:
        ref_tokens = {t for t in re.split(r"[\s=+*/^(),]+", ref) if len(t) > 2}
        sub_tokens = {t for t in re.split(r"[\s=+*/^(),]+", sub) if len(t) > 2}
        if ref_tokens and not ref_tokens.issubset(sub_tokens | set(re.split(r"[\s=+*/^(),]+", exp))):
            return "formule"

    # 4. Méthode : parenthèses déséquilibrées.
    if _error_balance(sub):
        return "methode"

    return "aucune"


def evaluate_step(
    *,
    step: SolutionStep,
    submission: str,
    reference: str = "",
    attempts: int = 1,
) -> StepEvaluation:
    """Évalue une soumission d'étape via le moteur §20 + classification.

    score : vient du moteur §20 (même formule que evaluate_answer) —
    le moteur calcule le score déterministe quand une référence est
    fournie, sinon NULL = pas de preuve déterministe → le moteur est
    la seule autorité (il ne décide jamais seul, il constate).
    """
    result = ENGINE.evaluate(
        activity_id="problem-subgraph",
        activity_type="problem_step",
        answer=submission or "",
        subject="mathematiques",
        topic=step.kind or "problem",
        reference=reference or step.expected or "",
        score=_math_exact_score(submission or "", reference or ""),
        feedback="",
    )

    # §19 : jamais de sanction sans preuve déterministe. "unclear" (pas
    # de score calculé) reste "unclear" — le node décide d'avancer sans
    # pénalité (le guide/agent conversationnel oriente). "incorrect"
    # n'est émis que si un score déterministe existe et le contredit.
    if result.verdict == "unclear":
        verdict: str = "unclear"
    elif result.verdict in ("correct", "mostly_correct"):
        verdict = "correct"
    else:
        verdict = "incorrect"
    error_kind = classify_error_kind(
        submission, step.expected or "", reference or ""
    )

    if verdict == "unclear":
        feedback = "Étape non tranchée (pas de preuve déterministe) — je te guide."
    else:
        feedback = result.feedback or (
            "Étape correcte." if verdict == "correct" else "Étape à corriger."
        )
    if error_kind != "aucune":
        feedback = f"{feedback} Erreur classifiée : {error_kind}."

    return StepEvaluation(
        step_id=step.step_id,
        verdict=verdict,  # type: ignore[arg-type]
        score=result.score,
        error_kind=error_kind,
        attempts=max(1, attempts),
        feedback=feedback,
        evidence=list(result.evidence),
    )


def _step_weight(attempts: int) -> float:
    """Poids de réussite d'une étape : 1er essai = 1.0, sinon décroît."""
    if attempts <= 1:
        return 1.0
    return round(max(0.0, 1.0 - 0.25 * (attempts - 1)), 2)


def compute_rigor(step_evaluations: list[StepEvaluation]) -> dict:
    """Score de rigueur agrégé (§21) depuis les évaluations d'étapes.

    - score     : moyenne pondérée des étapes correctes (pénalité
                  retries) ; 0 si aucune étape.
    - solved    : toutes les étapes correctes (aucune échec définitif).
    - errors    : agrégat des erreurs classifiées (trace §21).
    """
    if not step_evaluations:
        return {"score": 0.0, "solved": False, "attempts_count": 0, "errors": []}

    total = 0.0
    attempts_count = 0
    all_correct = True
    errors: list[dict] = []

    for ev in step_evaluations:
        attempts_count += ev.attempts
        weight = _step_weight(ev.attempts)
        # §19 : sans preuve déterministe ("unclear") l'étape est NEUTRE —
        # ni pénalisée (score 1.0) ni considérée comme un échec. Seul un
        # verdict "incorrect" (score déterministe < seuil) sanctionne.
        score = ev.score if ev.score is not None else (1.0 if ev.verdict in ("correct", "unclear") else 0.0)
        total += weight * score
        if ev.verdict == "incorrect":
            all_correct = False
        if ev.error_kind != "aucune":
            errors.append({"step_id": ev.step_id, "error_kind": ev.error_kind})

    n = len(step_evaluations)
    return {
        "score": round(total / n, 3),
        "solved": all_correct,
        "attempts_count": attempts_count,
        "errors": errors,
    }


__all__ = [
    "evaluate_step",
    "classify_error_kind",
    "compute_rigor",
]