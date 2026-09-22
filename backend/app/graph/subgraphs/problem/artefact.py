# Problem Subgraph — ARTEFACT Markdown résumant la résolution (§21).
#
# build_artefact : assemble un document Markdown structuré :
#   - énoncé (nettoyé, jamais la réponse interne)
#   - classe / parsing (synthèse, pas le détail brut)
#   - plan interne (étapes attendues)
#   - évaluations d'étapes (verdicts, erreurs classifiées)
#   - score de rigueur + conclusion
# DÉTERMINISTE : aucun contenu ne dépend d'un LLM.
from __future__ import annotations

from app.schemas.problem import (
    ParsedStatement,
    StepEvaluation,
)
from app.graph.subgraphs.problem.planner import SolutionStep


def _fmt_bool(value: bool) -> str:
    return "oui" if value else "non"


def build_artefact(
    *,
    statement: str,
    parsed: ParsedStatement | None = None,
    plan: list[SolutionStep] | None = None,
    step_evaluations: list[StepEvaluation] | None = None,
    rigor: dict | None = None,
    final_verdict: str = "",
) -> str:
    """Construit l'artefact Markdown de la résolution (§21).

    Le strict minimum d'information pédagogique est exposé : on ne
    divulgue jamais la solution attendue des étapes (expected est vide
    dans le plan par design).
    """
    lines: list[str] = []
    lines.append("# Résolution — artefact")
    lines.append("")

    lines.append(f"## Énoncé\n\n{statement.strip()}\n" if statement else "## Énoncé\n")
    lines.append("")

    if parsed is not None:
        lines.append("## Analyse de l'énoncé")
        lines.append(f"- Classe : `{parsed.statement_class}`")
        if parsed.variables:
            lines.append(f"- Variables : {', '.join(parsed.variables)}")
        if parsed.units:
            lines.append(f"- Unités : {', '.join(parsed.units)}")
        if parsed.confidence:
            lines.append(f"- Confiance parsing : {parsed.confidence:.2f}")
        lines.append("")

    plan = plan or []
    if plan:
        lines.append("## Plan interne")
        for idx, step in enumerate(plan, start=1):
            lines.append(f"{idx}. {step.label}")
        lines.append("")

    evals = step_evaluations or []
    if evals:
        lines.append("## Étapes évaluées")
        for ev in evals:
            verdict = "✅" if ev.verdict == "correct" else "❌"
            err = "" if ev.error_kind == "aucune" else f" — erreur : {ev.error_kind}"
            score = f" (score {ev.score:.2f})" if ev.score is not None else ""
            attempts = f" — {ev.attempts} tentative(s)"
            lines.append(f"- {verdict} `{ev.step_id}`{err}{score}{attempts}")
        lines.append("")

    if rigor:
        lines.append("## Rigueur")
        lines.append(f"- Score de rigueur : {rigor.get('score', 0.0):.2f}")
        lines.append(f"- Résolu : {_fmt_bool(rigor.get('solved', False))}")
        lines.append(f"- Tentatives totales : {rigor.get('attempts_count', 0)}")
        errors = rigor.get("errors") or []
        if errors:
            err_detail = ", ".join(
                f"{e.get('step_id')}={e.get('error_kind')}" for e in errors
            )
            lines.append(f"- Erreurs classifiées : {err_detail}")
        lines.append("")

    if final_verdict:
        lines.append(f"## Verdict\n\n{final_verdict}\n")

    return "\n".join(lines).strip() + "\n"


__all__ = ["build_artefact"]