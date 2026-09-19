# Problem Subgraph — PARSING déterministe de l'énoncé (§21).
#
# parse_statement : règles lexicales pures (regex + dictionnaire
# pédagogique). Aucun LLM — un énoncé libre est mappé sur une classe
# (equation/derivee/integrale/...) et les variables/unités/verbes
# d'action sont extraits. Ce parsing alimente le plan interne et le
# guide ; il n'exécute AUCUNE résolution.
from __future__ import annotations

import re
import unicodedata

from app.graph.subgraphs.problem.schemas import (
    ParsedStatement,
    StatementClass,
)

# Verbes d'action / consignes (§21 : requested).
_REQUEST_VERBS: dict[str, tuple[str, ...]] = {
    "derivee": ("deriv", "derive"),
    "integrale": ("integr", "primitive"),
    "equation": ("resoudre", "solve"),
    "inequation": ("inequation", "signe de"),
    "factorisation": ("factoris", "developp"),
    "trigonometrie": ("cos", "sin", "tan", "trigono"),
    "geometrie": ("aire", "volume", "perimetre", "triangle"),
    "suite": ("suite", "raison", "terme general"),
    "probabilite": ("probabil", "esperance", "aleatoire"),
    "logique": ("implication", "contraposition", "raisonnement"),
}

# Unités SI + usuelles (§21 : erreurs unite).
_UNITS = (
    "km/h", "m/s", "deg",
    "m", "s", "kg", "mol", "a", "v", "j", "w", "hz", "pa", "n",
    "degre", "degres", "celsius",
    "km", "cm", "mm", "h", "min", "l", "g", "t",
    "eur", "euros",
)

# Dictionnaire des verbes de consigne génériques.
_GENERIC_VERBS = (
    "calcule", "deduis", "montre", "montrer", "verifie",
    "determine", "simplifie", "explique",
    "resous", "factorise", "exprimer", "trouve",
)

_VARIABLE_RE = re.compile(r"\b([a-zA-Z])\b")
_UNIT_RE = re.compile(r"\b(" + "|".join(re.escape(u) for u in _UNITS) + r")\b")
_ACTION_RE = re.compile(r"\b(" + "|".join(_GENERIC_VERBS) + r")\b")


def _normalize(text: str) -> str:
    """Minuscules + accents retirés (NFC vers ASCII)."""
    if not text:
        return ""
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def _detect_class(normalized: str) -> StatementClass:
    """Détecte la classe d'énoncé — première règle qui matche."""
    for cls in (
        "derivee", "integrale", "equation", "inequation",
        "factorisation", "trigonometrie", "geometrie", "suite",
        "probabilite", "logique",
    ):
        for token in _REQUEST_VERBS[cls]:
            if token in normalized:
                return cls  # type: ignore[return-value]
    if "=" in normalized:
        return "equation"
    return "autre"


def _keywords(normalized: str) -> list[str]:
    """Mots-clés pédagogiques significatifs présent l'énoncé."""
    found: list[str] = []
    for token in (
        "derive", "primitive", "equation", "inequation", "factor",
        "cos", "sin", "tan", "aire", "volume", "suite", "probabilite",
        "implication", "limite", "fonction", "racine", "entier", "strictement",
    ):
        if token in normalized and token not in found:
            found.append(token)
    return found


def parse_statement(statement: str) -> ParsedStatement:
    """Parse un énoncé libre en ParsedStatement (§21).

    DÉTERMINISTE : aucune sortie ne dépend d'un LLM ni de l'heure.
    """
    text = statement or ""
    normalized = _normalize(text)

    statement_class = _detect_class(normalized)

    variables: list[str] = []
    for m in _VARIABLE_RE.finditer(text):
        var = m.group(1).lower()
        if var not in variables and var not in ("a", "i", "n", "x"):
            variables.append(var)
    if statement_class in ("equation", "inequation") and "x" not in variables:
        variables.append("x")

    units: list[str] = []
    for m in _UNIT_RE.finditer(text):
        u = m.group(1)
        if u not in units:
            units.append(u)

    requested: list[str] = []
    for m in _ACTION_RE.finditer(text):
        verb = m.group(1)
        if verb not in requested:
            requested.append(verb)

    # Confiance : 1 classe détectée + variables/consignes → plus sûr.
    confidence = 0.0
    if statement_class != "autre":
        confidence += 0.6
    if variables:
        confidence += 0.2
    if requested:
        confidence += 0.2

    return ParsedStatement(
        normalized=normalized,
        statement_class=statement_class,
        variables=variables,
        units=units,
        keywords=_keywords(normalized),
        has_equation="=" in normalized,
        requested=requested,
        confidence=round(min(1.0, confidence), 2),
    )


__all__ = ["parse_statement"]