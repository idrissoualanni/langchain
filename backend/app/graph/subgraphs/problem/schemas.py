# Problem Subgraph — schémas du domaine (§21).
#
# Le ProblemSubgraph standardise la résolution d'énoncé PAS À PAS sans
# en refaire le moteur : le scoring de chaque étape s'appuie sur le
# moteur d'évaluation §20 (EvaluationEngine), la saisie/la persistance
# sur l'ActivityStore de Phase 2. Ce module ne contient QUE les types
# purs du domaine Problem (aucune logique de graphe).
#
# Erreurs classifiées (§21) : unite / formule / signe / methode.
# Score de rigueur : agrégat des scores d'étapes (pénalité retries).
#
# Préservé depuis le legacy V5.2 / prévu §21 :
#   - parsing (énoncé → concepts/variables/inconnues)
#   - plan interne (étapes attendues)
#   - guide pas à pas (hint par étape)
#   - erreurs classees unite/formule/signe/methode
#   - score de rigueur
#   - artefact Markdown
#   - événements SSE
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# Erreurs classifiées d'une étape (§21). "aucune" = étape correcte.
ErrorKind = Literal["unite", "formule", "signe", "methode", "aucune"]

# Verdicts possibles d'une étape.
StepVerdict = Literal["correct", "incorrect", "hint"]

# Classes d'énoncé détectées au parsing (§21).
StatementClass = Literal[
    "derivee",
    "integrale",
    "equation",
    "inequation",
    "factorisation",
    "trigonometrie",
    "geometrie",
    "suite",
    "probabilite",
    "logique",
    "autre",
]


class ParsedStatement(BaseModel):
    """Résultat du parsing déterministe d'un énoncé (§21).

    Extrait les informations saillantes UTILES à la résolution :
    classe d'énoncé, variables, unités, formule attendue le cas échéant.
    Aucun LLM : règles lexicales pures (REGEX + dictionnaire).
    """

    model_config = {"extra": "forbid"}

    normalized: str = Field(
        default="",
        description="Énoncé normalisé (minuscules, accents retirés)",
    )
    statement_class: StatementClass = Field(
        default="autre",
        description="Classe d'énoncé détectée (détermination, pas jugement)",
    )
    variables: list[str] = Field(
        default_factory=list,
        description="Symboles variables détectés (ex: x, t, a)",
    )
    units: list[str] = Field(
        default_factory=list,
        description="Unités détectées (ex: m, s, kg, degre)",
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="Mots-clés pédagogiques significatifs détectés",
    )
    has_equation: bool = Field(
        default=False,
        description="L'énoncé contient une forme équationnelle (=)",
    )
    requested: list[str] = Field(
        default_factory=list,
        description="Consignes/verbes d'action (calcule, derive, resous...)",
    )
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Confiance du parsing [0..1]",
    )


class SolutionStep(BaseModel):
    """Étape attendue du plan interne (§21)."""

    model_config = {"extra": "forbid"}

    step_id: str = Field(
        default="",
        description="Identifiant d'étape (ex: step-1)",
    )
    label: str = Field(
        default="",
        description="Intitulé lisible de l'étape",
    )
    kind: str = Field(
        default="generic",
        description="Nature de l'étape (formuler, dériver, résoudre, "
        "vérifier, conclure)",
    )
    hint: str = Field(
        default="",
        description="Guide pas à pas pour cette étape (§21 guide)",
    )
    expected: str = Field(
        default="",
        description="Réponse attendue (pour l'évaluation déterministe)",
    )
    error_kind: ErrorKind = Field(
        default="aucune",
        description="Erreur classifiée à la dernière tentative",
    )


class StepEvaluation(BaseModel):
    """Évaluation déterministe d'UNE soumission d'étape (§21)."""

    model_config = {"extra": "forbid"}

    step_id: str = Field(
        default="",
        description="Étape évaluée",
    )
    verdict: StepVerdict = Field(
        default="incorrect",
        description="Verdict de l'étape",
    )
    score: float | None = Field(
        default=None, ge=0.0, le=1.0,
        description="Score normalisé [0..1] (moteur §20)",  # suite
    )
    error_kind: ErrorKind = Field(
        default="aucune",
        description="Erreur classifiée (unite/formule/signe/methode)",
    )
    attempts: int = Field(
        default=1, ge=1,
        description="Tentatives consommées pour cette étape",
    )
    feedback: str = Field(
        default="",
        description="Retour lisible à l'étudiant",
    )
    evidence: list[dict] = Field(
        default_factory=list,
        description="Preuves de l'évaluation (evidence §20)",
    )


class RigorScore(BaseModel):
    """Score de rigueur et de réussite global (§21)."""

    model_config = {"extra": "forbid"}

    score: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Score de rigueur agrégé [0..1]",
    )
    solved: bool = Field(
        default=False,
        description="Toutes les étapes correctement résolues du premier "
        "ou dernier essai (aucune étape bloquée)",
    )
    attempts_count: int = Field(
        default=0, ge=0,
        description="Total des tentatives",
    )
    errors: list[dict] = Field(
        default_factory=list,
        description="Erreurs classifiées agrégées (error_kind/step_id)",
    )


__all__ = [
    "ErrorKind",
    "StepVerdict",
    "StatementClass",
    "ParsedStatement",
    "SolutionStep",
    "StepEvaluation",
    "RigorScore",
]