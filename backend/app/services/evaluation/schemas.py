# Evaluation Schemas (Phase 2) — contrat d'évaluation §20.
#
# Séparation §18 : SCORING ≠ MISE À JOUR DU PROFIL. Le Evaluation
# Engine produit UNIQUEMENT un EvaluationResult ; la traduction en
# LearningObservation (et la mise à jour du profil) est une étape
# séparée (evaluation.observations / learning_profile).
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Dimensions d'évaluation §19 (séparées, jamais mélangées).
EvaluationDimension = Literal[
    "deterministic",  # règles déterministes (couverture termes...)
    "execution",      # tests / runtime (§19 dimensions code)
    "static",         # analyse statique (lint, sécurité)
    "domain_rules",   # règles de domaine pédagogiques
    "llm",            # LLM evaluation — dernier recours
]

# Médailes de verdict (pas de "note" opaque).
Verdict = Literal[
    "correct",
    "mostly_correct",
    "partial",
    "incorrect",
    "unclear",
    "error",
]


class EvaluationResult(BaseModel):
    """Résultat d'évaluation structuré (§20).

    Produit par le Evaluation Engine. Les détails internes du
    scoring NE sont PAS exposés : seuls score/verdict synthétiques et
    la liste d'evidence (traçable, non-décisionnelle).
    """

    model_config = {"extra": "forbid"}

    activity_id: str = Field(
        default="", description="Activité évaluée (§15)"
    )
    score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Score normalisé [0..1] — None si non quantifiable",
    )
    verdict: Verdict = Field(
        default="partial", description="Verdict de correction §20"
    )
    strengths: list[str] = Field(
        default_factory=list,
        description="Points forts observés (concrets, liés au sujet)",
    )
    weaknesses: list[str] = Field(
        default_factory=list,
        description="Points faibles observés (concrets, liés au sujet)",
    )
    feedback: str = Field(
        default="", description="Retour formatif lisible (§11)"
    )
    evidence: list[dict] = Field(
        default_factory=list,
        description="Preuves traçables [{d, value, ...}] — pour "
        "observabilité, jamais le score interne brut",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confiance dans le verdict [0..1]",
    )
    strategy: list[str] = Field(
        default_factory=list,
        description="Dimensions utilisées, ordre de priorité §19",
    )


def make_evaluation(
    *,
    activity_id: str = "",
    score: float | None = None,
    verdict: Verdict = "partial",
    strengths: list[str] | None = None,
    weaknesses: list[str] | None = None,
    feedback: str = "",
    evidence: list[dict] | None = None,
    confidence: float = 1.0,
    strategy: list[str] | None = None,
) -> EvaluationResult:
    """Constructeur validé (évite les champs hors contrat)."""
    return EvaluationResult(
        activity_id=activity_id,
        score=score,
        verdict=verdict,
        strengths=list(strengths or []),
        weaknesses=list(weaknesses or []),
        feedback=feedback,
        evidence=list(evidence or []),
        confidence=confidence,
        strategy=list(strategy or ["deterministic"]),
    )


__all__ = [
    "EvaluationDimension",
    "Verdict",
    "EvaluationResult",
    "make_evaluation",
]