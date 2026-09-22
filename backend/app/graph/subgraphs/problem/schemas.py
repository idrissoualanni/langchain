# SHIM de compatibilité (refactor — phase migration).
#
# Les schémas du domaine Problem ont déménagé vers
# app/schemas/problem.py. SUPPRESSION prévue phase cleanup (§30).
from app.schemas.problem import (
    ErrorKind,
    ParsedStatement,
    RigorScore,
    SolutionStep,
    StatementClass,
    StepEvaluation,
    StepVerdict,
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
