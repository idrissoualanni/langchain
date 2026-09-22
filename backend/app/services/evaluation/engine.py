# Evaluation Engine (Phase 2) — §18/§19.
#
# Sépare le SCORING de la MISE À JOUR DU PROFIL (§18) :
#
#   Answer → EvaluationEngine.evaluate() → EvaluationResult
#   → observation (evaluation/observations.py) → Learning Profile
#
# Stratégie §19 (priorité stricte, jamais l'inverse) :
#   deterministic → execution/tests → domain_rules → llm
#
# Le LLM NE décide JAMAIS seul quand une preuve déterministe existe.
# Pour le code, tests/lint/runtime/static/LLM restent des dimensions
# SÉPARÉES (CodingSubgraph, Phase 4) — ici on couvre l'évaluation
# pédagogique déterministe existante (evaluate_answer V5.2) que l'on
# standardise SANS la réécrire.
from __future__ import annotations

from typing import Any

from app.schemas.activity import make_result
from app.services.evaluation.schemas import (
    EvaluationResult,
    Verdict,
    make_evaluation,
)
from app.services.evaluation.text_scoring import score_course_answer


def _verdict_for(score: float | None) -> Verdict:
    """Verdict depuis un score normalisé [0..1] — même seuils que
    le scoring historique V5.2 (>=0.75 correct, >=0.4 partial)."""
    if score is None:
        return "unclear"
    if score >= 0.75:
        return "correct"
    if score >= 0.4:
        return "partial"
    return "incorrect"


def _evidence_dict(*, dimension: str, **fields: Any) -> dict:
    """Entrée d'evidence traçable (jamais le score interne brut)."""
    return {"dimension": dimension, **fields}


class EvaluationEngine:
    """Moteur d'évaluation déterministe (scoring séparé du profil).

    Une instance uniquement (stateless). Les méthodes delegates
    s'appuient sur les implémentations réelles existantes — le but
    est d'encapsuler, pas de recomputer en parallèle.
    """

    # Ordre de priorité §19 — le moteur essaye la première dimension
    # qui peut produire un verdict avec une PREUVE.
    STRATEGY_ORDER = ("deterministic", "execution", "domain_rules", "llm")

    def evaluate(
        self,
        *,
        activity_id: str,
        activity_type: str,
        answer: str,
        subject: str = "",
        topic: str = "",
        reference: str = "",
        score: float | None = None,
        covered: list[str] | None = None,
        missing: list[str] | None = None,
        feedback: str = "",
    ) -> EvaluationResult:
        """Produit un EvaluationResult normalisé (§20).

        Le scoring DÉTERMINISTE (§19) est calculé ici quand une
        référence cours/document est fournie et aucun score n'est
        pré-computé (formule canonique text_scoring.score_course_answer).
        Quand le caller (evaluate_answer) passe déjà score/covered/
        missing — issus de la MÊME formule — on les architecture au
        contrat sans recomputer ni diverger.
        """
        if score is None and reference:
            score, computed_covered, computed_missing = score_course_answer(
                reference, answer or ""
            )
            covered = covered or computed_covered
            missing = missing or computed_missing

        verdict = _verdict_for(score)
        strategy: list[str] = ["deterministic"]
        evidence: list[dict] = []

        if score is not None:
            evidence.append(
                _evidence_dict(
                    dimension="deterministic",
                    activity_type=activity_type,
                    covered=len(covered or []),
                    missing=len(missing or []),
                )
            )

        strengths = [s for s in (covered or []) if s][:6]
        weaknesses = [s for s in (missing or []) if s][:6]

        return make_evaluation(
            activity_id=activity_id,
            score=score,
            verdict=verdict,
            strengths=strengths,
            weaknesses=weaknesses,
            feedback=feedback,
            evidence=evidence,
            confidence=0.9,
            strategy=strategy,
        )


# Instance canonique (stateless) — aucun état à partager.
ENGINE = EvaluationEngine()


def evaluate_activity(
    *,
    activity_id: str,
    activity_type: str,
    answer: str,
    subject: str = "",
    topic: str = "",
    reference: str = "",
    score: float | None = None,
    covered: list[str] | None = None,
    missing: list[str] | None = None,
    feedback: str = "",
) -> EvaluationResult:
    """API publique du moteur → EvaluationResult (§20)."""
    return ENGINE.evaluate(
        activity_id=activity_id,
        activity_type=activity_type,
        answer=answer,
        subject=subject,
        topic=topic,
        reference=reference,
        score=score,
        covered=covered,
        missing=missing,
        feedback=feedback,
    )


def evaluation_to_result_dict(result: EvaluationResult) -> dict:
    """EvaluationResult → dict stockable dans activity["result"]
    (§15 result) — aligné make_result (voyant §20)."""
    return make_result(
        score=result.score,
        verdict=result.verdict,
        strengths=result.strengths,
        weaknesses=result.weaknesses,
        feedback=result.feedback,
        evidence=result.evidence,
        confidence=result.confidence,
    )


def update_activity_with_result(
    activity: dict, result: EvaluationResult
) -> dict:
    """Ajoute le résultat §20 dans activity (champ "result", ADDITIF).

    NE modifie PAS last_evaluation/attempts/statut : la shape V5.2
    (score/verdict humain/covered/missing) reste écrite par le tool
    caller — ceci est une couche d'architecture, jamais une réécriture.
    """
    if not isinstance(activity, dict):
        return activity
    activity["result"] = evaluation_to_result_dict(result)
    return activity


__all__ = [
    "EvaluationEngine",
    "ENGINE",
    "evaluate_activity",
    "evaluation_to_result_dict",
    "update_activity_with_result",
]