# Problem Subgraph — NODES (§21) + graphe compilé.
#
# Pipeline cible §21 :
#
#   START
#    ↓
#   parse         → parse_statement (ParsedStatement)
#    ↓
#   plan          → build_plan (SolutionStep[])
#    ↓
#   guide         → build_guide (message d'orientation, hint courant)
#    ↓
#   evaluate_step → evaluate_step (moteur §20 + classification erreur)
#    ↓
#   validate      → compute_rigor + verdict final (ProblemResult §8)
#    ↓
#   artifact      → build_artefact (Markdown)
#    ↓
#   END
#
# Chaque node est MINCE : il lit l'état, appelle LA fonction pure du
# domaine, sérialise une "étape" dans l'état et journalise un événement
# (SSE, log_event). Aucun LLM dans le sous-graphe — le sous-graphe
# agentique conversationnel reste responsable de la rédaction finale.
#
# DÉTERMINISTE (testable sans serveur) : pas d'appel réseau, pas
# d'instanciation d'agent.
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.schemas.workflow import ProblemResult
from app.graph.subgraphs.problem.artefact import build_artefact
from app.graph.subgraphs.problem.evaluator import compute_rigor, evaluate_step
from app.graph.subgraphs.problem.parser import parse_statement
from app.graph.subgraphs.problem.planner import SolutionStep, build_guide, build_plan
from app.schemas.problem import ParsedStatement, StepEvaluation
from app.graph.subgraphs.problem.state import ProblemState
from app.logging.events import log_event

# Tentatives max par étape (retry policy §21) puis on avance quand même
# (le sous-graphe ne bloque pas la conversation).
MAX_ATTEMPTS = 3


def _ids(state) -> tuple[str, str]:
    user_id = (state or {}).get("user_id") or ""
    thread_id = (state or {}).get("thread_id") or ""
    return user_id, thread_id


def _log(name: str, message: str, state, level: str = "INFO", extra: dict | None = None):
    user_id, thread_id = _ids(state)
    log_event(
        name,
        level=level,
        message=message,
        user_id=user_id,
        thread_id=thread_id,
        extra={"operation": "problem_subgraph", **(extra or {})},
    )


def _rehydrate_plan(plan: list[dict]) -> list[SolutionStep]:
    """plan (list[dict]) → list[SolutionStep] avec expected VIDE."""
    steps: list[SolutionStep] = []
    for i, p in enumerate(plan):
        steps.append(
            SolutionStep(
                step_id=p.get("step_id", f"step-{i + 1}"),
                label=p.get("label", ""),
                kind=p.get("kind", "generic"),
                hint=p.get("hint", ""),
                expected="",
                error_kind=p.get("error_kind", "aucune"),
            )
        )
    return steps


def _parsed_from_state(state) -> ParsedStatement:
    parsed_data = (state or {}).get("parsed") or {}
    return ParsedStatement(
        normalized=parsed_data.get("normalized", ""),
        statement_class=parsed_data.get("statement_class", "autre"),
        variables=parsed_data.get("variables", []),
        units=parsed_data.get("units", []),
        keywords=parsed_data.get("keywords", []),
        has_equation=parsed_data.get("has_equation", False),
        requested=parsed_data.get("requested", []),
        confidence=float(parsed_data.get("confidence", 0.0) or 0.0),
    )


# ------------------------------------------------------------
# PARSE node
# ------------------------------------------------------------
def parse_node(state) -> dict:
    """PARSE — parsing déterministe de l'énoncé (§21).

    REPLAY-safe : si un parsing ET un plan existent déjà dans l'état
    (continuation pas-à-pas, current_index > 0), on NE RÉINITIALISE
    RIEN — on laisse l'état de progression intact et on passe à PLAN.
    """
    statement = (state or {}).get("statement") or (state or {}).get("query") or ""
    existing = (state or {}).get("parsed") or {}
    plan = (state or {}).get("plan") or []
    if existing and plan:
        # Résolution déjà amorcée (parse + plan présents) : l'état de
        # progression est CONSERVÉ. Un nouveau problème implique un
        # état neuf (nouvelle invocation / reset explicite).
        return {}

    parsed = parse_statement(statement)
    _log(
        "PROBLEM_PARSE",
        f"Problem parse | class={parsed.statement_class} | "
        f"confidence={parsed.confidence}",
        state,
        extra={"statement_class": parsed.statement_class},
    )
    return {
        "parsed": parsed.model_dump(),
        "plan": [],
        "current_index": 0,
        "attempts": 0,
        "step_scores": [],
        "step_feedback": [],
        "last_error": {},
        "rigor": {"score": 0.0, "solved": False, "attempts_count": 0, "errors": []},
        "next_action": "plan",
    }


# ------------------------------------------------------------
# PLAN node
# ------------------------------------------------------------
def plan_node(state) -> dict:
    """PLAN — plan interne d'étapes attendues (§21).

    REPLAY-safe : le plan déjà présent (continuation) est conservé.
    """
    existing_plan = (state or {}).get("plan") or []
    if existing_plan:
        return {}
    parsed_data = (state or {}).get("parsed") or {}
    statement = (state or {}).get("statement") or (state or {}).get("query") or ""
    parsed = parse_statement(statement) if statement else None
    if parsed is None or (parsed.statement_class == "autre"
                          and parsed_data.get("statement_class")
                          and parsed_data["statement_class"] != "autre"):
        # Énoncé vide ou hors reconnaissance : on garde le parsing
        # stocké par PARSE node.
        parsed = _parsed_from_state(state)
    plan = build_plan(parsed)
    _log(
        "PROBLEM_PLAN",
        f"Problem plan | steps={len(plan)}",
        state,
        extra={"steps": len(plan)},
    )
    return {
        "plan": [s.model_dump() for s in plan],
        "next_action": "guide",
    }


# ------------------------------------------------------------
# GUIDE node
# ------------------------------------------------------------
def guide_node(state) -> dict:
    """GUIDE — guide pas à pas pour l'étape courante (§21)."""
    plan = [dict(p) for p in (state or {}).get("plan") or []]
    current_index = int((state or {}).get("current_index") or 0)
    if not plan:
        return {}
    steps = _rehydrate_plan(plan)
    guide = build_guide(steps, current_index)
    _log(
        "PROBLEM_GUIDE",
        f"Problem guide | {guide.splitlines()[0] if guide else ''}",
        state,
    )
    return {"guide_message": guide}


# ------------------------------------------------------------
# EVALUATE_STEP node (pas à pas : UNE soumission par invocation)
# ------------------------------------------------------------
def evaluate_step_node(state) -> dict:
    """EVALUATE_STEP — évalue la soumission de l'étape courante (§21).

    La soumission vient du canal `submission` (saisie de l'étudiant
    pour l'étape courante). Une invocation n'évalue qu'UNE étape :
      - aucune soumission  → next_action="wait" (on attend la réponse,
        le guide a déjà été produit par guide_node) ;
      - correct/unclear    → étape validée SANS pénalité (une étape
        "unclear" = pas de preuve déterministe §19, on avance) ;
      - incorrect          → retry sur la MÊME étape (soumission
        conservée) jusqu'à MAX_ATTEMPTS puis on avance quand même (le
        sous-graphe ne bloque jamais la conversation).
    Routeur (route_after_evaluate_step) :
      - "validate" → VALIDATE (fin du plan)
      - "retry"    → GUIDE (même étape, nouvelle tentative)
      - "wait"     → END (attente de la soumission de l'étape en cours)
    """
    plan = [dict(p) for p in (state or {}).get("plan") or []]
    current_index = int((state or {}).get("current_index") or 0)
    if not plan or current_index >= len(plan):
        return {"next_action": "validate"}

    steps = _rehydrate_plan(plan)
    step_obj = steps[current_index]

    submission = str((state or {}).get("submission") or "").strip()
    if not submission:
        # Pas encore de réponse : on attend une soumission. Le guide de
        # l'étape courante a déjà été produit par guide_node.
        return {"next_action": "wait"}

    reference = str((state or {}).get("reference") or "")
    attempts = int((state or {}).get("attempts") or 0) + 1

    evaluation = evaluate_step(
        step=step_obj,
        submission=submission,
        reference=reference,
        attempts=attempts,
    )

    step_scores = [dict(s) for s in (state or {}).get("step_scores") or []]
    step_feedback = [dict(f) for f in (state or {}).get("step_feedback") or []]

    # §19 : PAS de sanction sans preuve déterministe. "unclear" avance
    # sans pénalité ; "correct" valide l'étape. "incorrect" (score
    # déterministe < seuil) déclenche un retry limité.
    if evaluation.verdict in ("correct", "unclear"):
        step_scores.append(
            {
                "step_id": step_obj.step_id,
                "correct": True,
                "attempts": attempts,
                "score": evaluation.score,
            }
        )
        step_feedback.append(evaluation.model_dump())
        next_index = current_index + 1
        _log(
            "PROBLEM_STEP_OK",
            f"Problem step ok | {step_obj.step_id} | attempts={attempts}",
            state,
            extra={"step_id": step_obj.step_id, "attempts": attempts},
        )
        return {
            "step_scores": step_scores,
            "step_feedback": step_feedback,
            "current_index": next_index,
            "attempts": 0,
            "submission": "",
            "last_error": {
                "step_id": step_obj.step_id,
                "error_kind": "aucune",
                "attempts": attempts,
            },
            "next_action": "validate" if next_index >= len(plan) else "wait",
        }

    # Incorrect (échec déterministe SANS retry restant) : on avance
    # après MAX_ATTEMPTS — le sous-graphe ne bloque pas la conversation
    # et l'erreur reste tracée (rigor, feedback, artifact).
    if attempts >= MAX_ATTEMPTS:
        step_scores.append(
            {"step_id": step_obj.step_id, "correct": False, "attempts": attempts}
        )
        step_feedback.append(evaluation.model_dump())
        _log(
            "PROBLEM_STEP_BLOCKED",
            f"Problem step blocked | {step_obj.step_id} | attempts={attempts}",
            state,
            level="WARNING",
            extra={
                "step_id": step_obj.step_id,
                "attempts": attempts,
                "error_kind": evaluation.error_kind,
            },
        )
        next_index = current_index + 1
        return {
            "step_scores": step_scores,
            "step_feedback": step_feedback,
            "current_index": next_index,
            "attempts": 0,
            "submission": "",
            "last_error": {
                "step_id": step_obj.step_id,
                "error_kind": evaluation.error_kind,
                "attempts": attempts,
            },
            "next_action": "validate" if next_index >= len(plan) else "wait",
        }

    # Retry : SOUMISSION CONSERVÉE, la boucle ↺ repasse par GUIDE pour
    # produire un nouvel indice avant la réévaluation.
    _log(
        "PROBLEM_STEP_RETRY",
        f"Problem step retry | {step_obj.step_id} | attempts={attempts} | "
        f"error={evaluation.error_kind}",
        state,
        extra={
            "step_id": step_obj.step_id,
            "attempts": attempts,
            "error_kind": evaluation.error_kind,
        },
    )
    return {
        "attempts": attempts,
        "last_error": {
            "step_id": step_obj.step_id,
            "error_kind": evaluation.error_kind,
            "attempts": attempts,
        },
        "next_action": "retry",
    }


def route_after_evaluate_step(state) -> str:
    """Routeur INTERNE de la boucle ↺ (§21).

    L'état contient next_action posé par evaluate_step_node.
      - "validate" → node VALIDATE (fin du plan / étape irrécupérable)
      - "retry"    → retour GUIDE (même étape, nouvelle tentative)
      - "wait"     → END (on attend la soumission de l'étape courante)
    """
    action = (state or {}).get("next_action") or "wait"
    if action == "validate":
        return "validate"
    if action == "retry":
        return "guide"
    return END


# ------------------------------------------------------------
# VALIDATE node — verdict final + rigor
# ------------------------------------------------------------
def validate_node(state) -> dict:
    """VALIDATE — score de rigueur + verdict final (§21)."""
    evals = [
        StepEvaluation(**dict(f))
        for f in (state or {}).get("step_feedback") or []
    ]
    rigor = compute_rigor(evals)
    verdict = (
        "correct"
        if rigor["solved"]
        else ("plan_incomplet" if evals else "mal_formule")
    )
    _log(
        "PROBLEM_VALIDATE",
        f"Problem validate | verdict={verdict} | rigor={rigor['score']}",
        state,
        extra={"verdict": verdict, "rigor": rigor["score"]},
    )
    return {
        "rigor": rigor,
        "verdict": verdict,
        "next_action": "artifact",
    }


# ------------------------------------------------------------
# ARTIFACT node — Markdown final + ProblemResult (§8)
# ------------------------------------------------------------
def artifact_node(state) -> dict:
    """ARTIFACT — génère l'artefact Markdown (§21) et le ProblemResult."""
    plan = [dict(p) for p in (state or {}).get("plan") or []]
    plan_objs = _rehydrate_plan(plan)
    evals = [
        StepEvaluation(**dict(f))
        for f in (state or {}).get("step_feedback") or []
    ]
    parsed = _parsed_from_state(state)
    rigor = (state or {}).get("rigor") or {
        "score": 0.0,
        "solved": False,
        "attempts_count": 0,
        "errors": [],
    }
    verdict = (state or {}).get("verdict") or ""
    statement = (state or {}).get("statement") or (state or {}).get("query") or ""

    markdown = build_artefact(
        statement=statement,
        parsed=parsed,
        plan=plan_objs,
        step_evaluations=evals,
        rigor=rigor,
        final_verdict=verdict,
    )

    result = ProblemResult(
        workflow="problem",
        status="ok" if rigor.get("solved") else "partial",
        message=(
            "Résolution pas à pas terminée"
            if rigor.get("solved")
            else "Résolution terminée avec erreurs à corriger"
        ),
        understanding={
            "statement_class": parsed.statement_class,
            "variables": parsed.variables,
            "units": parsed.units,
            "requested": parsed.requested,
        },
        solution_steps=[
            {"step_id": s.step_id, "label": s.label} for s in plan_objs
        ],
        verdict=verdict,
        confidence=rigor.get("score", 0.0),
        markdown=markdown,
    )

    _log(
        "PROBLEM_ARTIFACT",
        f"Problem artifact | markdown_chars={len(markdown)}",
        state,
        extra={"markdown_chars": len(markdown)},
    )

    return {
        "workflow_result": result.model_dump(),
        "next_action": "end",
    }


# ------------------------------------------------------------
# Compilation
# ------------------------------------------------------------
def compile_problem_subgraph():
    """Compile le ProblemSubgraph (§21) sur ProblemState.

    Aucun checkpointer/store requis : le sous-graphe est DÉTERMINISTE
    et stateless (l'état transite par l'invocation). Il peut être
    ajouté comme node du Main Graph via add_node("problem", ...) — les
    champs partagés (workflow_result) transitent, les champs internes
    restent contenus.
    """
    graph = StateGraph(ProblemState)

    graph.add_node("parse", parse_node)
    graph.add_node("plan", plan_node)
    graph.add_node("guide", guide_node)
    graph.add_node("evaluate_step", evaluate_step_node)
    graph.add_node("validate", validate_node)
    graph.add_node("artifact", artifact_node)

    graph.add_edge(START, "parse")
    graph.add_edge("parse", "plan")
    graph.add_edge("plan", "guide")
    graph.add_edge("guide", "evaluate_step")

    graph.add_conditional_edges(
        "evaluate_step",
        route_after_evaluate_step,
        {"guide": "guide", "validate": "validate", END: END},
    )

    graph.add_edge("validate", "artifact")
    graph.add_edge("artifact", END)

    return graph.compile()


__all__ = [
    "compile_problem_subgraph",
    "parse_node",
    "plan_node",
    "guide_node",
    "evaluate_step_node",
    "route_after_evaluate_step",
    "validate_node",
    "artifact_node",
    "MAX_ATTEMPTS",
]