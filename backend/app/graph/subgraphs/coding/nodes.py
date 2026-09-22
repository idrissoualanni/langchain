# CODING Subgraph — nodes + assemblage (§22-§25).
#
# Pipeline : START → analyze_task → execute_action ↺ → evaluate →
# generate_learning_signals → (finalize | finalize_with_limit) → END.
# Le résultat est produit dans CodingResult (contrat INTERNE du
# subgraph) ; le node CODING du Main Graph l'adapte vers le contrat §8
# (app/schemas/workflow.py, cf. app/graph/nodes/coding.py).
#
# DÉPENDANCES : exécution isolée (infrastructure/sandbox), engine
# d'apprentissage (services/learning), traçabilité (observability).
from typing import Any, Optional

from langgraph.graph import START, END, StateGraph
from pydantic import BaseModel, Field

from app.graph.subgraphs.coding.state import CodingState
from app.infrastructure.observability.langsmith_client import traceable_agent_action
from app.infrastructure.sandbox.executor import execute_code
from app.tools.coding import (
    analyze_code_tool,
    explain_error_tool,
)


class CodingResult(BaseModel):
    """Résultat structuré du CodingSubgraph (contrat INTERNE)."""
    success: bool
    status: str  # success, failed, timeout, security_violation, max_iterations
    result: dict[str, Any] = Field(default_factory=dict)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    code: Optional[str] = None
    test_results: Optional[list[dict[str, Any]]] = None
    learning_signals: list[dict[str, Any]] = Field(default_factory=list)


@traceable_agent_action(name="coding_analyze_task", run_type="chain")
def analyze_task(state: CodingState) -> dict[str, Any]:
    """Analyse la demande de codage pour identifier le type de tâche."""
    request_lower = state["request"].lower()

    if any(kw in request_lower for kw in ["debug", "erreur", "bug", "fix", "corriger"]):
        task_type = "debug"
    elif any(kw in request_lower for kw in ["test", "tester", "valider"]):
        task_type = "test"
    elif any(kw in request_lower for kw in ["explique", "explain", "comprendre"]):
        task_type = "explain"
    elif any(kw in request_lower for kw in ["modif", "edit", "change", "update"]):
        task_type = "edit"
    else:
        task_type = "write"

    language = state.get("language") or "python"
    if "python" in request_lower:
        language = "python"
    elif "javascript" in request_lower or "js" in request_lower:
        language = "javascript"

    return {
        **state,
        "task_type": task_type,
        "language": language,
        "iteration": state["iteration"] + 1,
    }


@traceable_agent_action(name="coding_execute_action", run_type="tool")
def execute_action(state: CodingState) -> dict[str, Any]:
    """Exécute l'action de codage (write/debug/test/explain).

    Sécurité : le code fourni est TOUJOURS scanné (patterns interdits
    + imports dangereux) avant tout traitement, quel que soit le type
    de tâche — une violation stoppe le workflow (finalize_with_limit).
    """
    task_type = state["task_type"]
    request = state["request"]

    errors = list(state.get("errors", []))
    observations = list(state.get("observations", []))
    test_results = list(state.get("test_results", []))

    try:
        # Scan sécurité statique (§24) — même si la tâche ne va pas
        # exécuter le code ici (write/edit/explain), le sandbox bloque
        # ces patterns à l'exécution : on les détecte EN AMONT.
        from app.infrastructure.sandbox.executor import (
            ScanResult,
            scan_code,
        )

        scan = scan_code(state.get("code") or "")
        if scan.security_violation:
            errors.append({
                "type": "security_violation",
                "details": scan.security_details,
            })

        if task_type == "debug":
            result = explain_error_tool.invoke({
                "code": state.get("code", ""),
                "error_message": request,
                "error_type": None,
            })

            if result.success and result.data:
                observations.append({"type": "diagnosis", "data": result.data})
            else:
                errors.append({"type": "diagnosis_failed", "message": result.error})

        elif task_type == "test":
            if state.get("code"):
                exec_result = execute_code(state["code"], timeout_seconds=10)

                test_results.append({
                    "success": exec_result.success,
                    "stdout": exec_result.stdout,
                    "stderr": exec_result.stderr,
                    "execution_time_ms": exec_result.execution_time_ms,
                })

                if not exec_result.success:
                    if exec_result.security_violation:
                        errors.append({
                            "type": "security_violation",
                            "details": exec_result.security_details,
                        })
                    else:
                        errors.append({
                            "type": "execution_error",
                            "message": exec_result.stderr,
                        })

        elif task_type in ["write", "edit"]:
            observations.append({
                "type": "action_prepared",
                "task_type": task_type,
                "ready_for_code_generation": True,
            })

        elif task_type == "explain":
            if state.get("code"):
                analysis = analyze_code_tool.invoke({
                    "code": state["code"],
                    "focus": "general",
                })

                if analysis.success and analysis.data:
                    observations.append({
                        "type": "code_analysis",
                        "data": analysis.data,
                    })

        return {
            **state,
            "errors": errors,
            "test_results": test_results,
            "observations": observations,
            "iteration": state["iteration"] + 1,
        }

    except Exception as e:
        errors.append({"type": "node_error", "message": str(e)})
        return {
            **state,
            "errors": errors,
            "iteration": state["iteration"] + 1,
        }


@traceable_agent_action(name="coding_evaluate", run_type="chain")
def evaluate(state: CodingState) -> dict[str, Any]:
    """Évalue le résultat du code (tests, qualité, conformité)."""
    observations = list(state.get("observations", []))

    test_results = state.get("test_results", [])
    errors = state.get("errors", [])

    all_tests_passed = all(r.get("success", False) for r in test_results) if test_results else False
    has_errors = len(errors) > 0

    evaluation = {
        "tests_passed": all_tests_passed,
        "tests_count": len(test_results),
        "has_errors": has_errors,
        "errors_count": len(errors),
        "quality_score": 0.0,
    }

    if all_tests_passed:
        evaluation["quality_score"] = 1.0
    elif has_errors:
        evaluation["quality_score"] = 0.0
    else:
        evaluation["quality_score"] = 0.5

    observations.append({"type": "evaluation", "data": evaluation})

    success = all_tests_passed and not has_errors

    return {
        **state,
        "success": success,
        "observations": observations,
        "final_result": {
            "evaluation": evaluation,
            "code": state.get("code"),
        },
    }


@traceable_agent_action(name="coding_generate_learning_signals", run_type="chain")
def generate_learning_signals(state: CodingState) -> dict[str, Any]:
    """Génère des signaux d'apprentissage pour le Learning Engine."""
    observations = list(state.get("observations", []))

    learning_signals = []

    if state["success"]:
        learning_signals.append({
            "type": "coding_success",
            "topic": state.get("topic", "unknown"),
            "subject": state.get("subject", "computer_science"),
            "evidence": "Code executed successfully with all tests passing",
        })
    else:
        learning_signals.append({
            "type": "coding_difficulty",
            "topic": state.get("topic", "unknown"),
            "subject": state.get("subject", "computer_science"),
            "evidence": "Code execution failed or tests did not pass",
            "errors": state.get("errors", []),
        })

    if state["iteration"] > 3:
        learning_signals.append({
            "type": "multiple_attempts",
            "attempts": state["iteration"],
            "topic": state.get("topic", "unknown"),
        })

    observations.append({"type": "learning_signals", "data": {"signals": learning_signals}})

    return {
        **state,
        "observations": observations,
    }


def should_continue(state: CodingState) -> str:
    """Décide si on continue la boucle ou si on termine."""
    if state["success"]:
        return "finalize"

    if state["iteration"] >= state["max_iterations"]:
        return "finalize_with_limit"

    if any(e.get("type") == "security_violation" for e in state.get("errors", [])):
        return "finalize_with_limit"

    return "continue_debug"


def finalize(state: CodingState) -> dict[str, Any]:
    """Finalise avec succès."""
    return {
        **state,
        "success": True,
    }


def finalize_with_limit(state: CodingState) -> dict[str, Any]:
    """Finalise avec échec (limite atteinte ou erreur critique)."""
    observations = list(state.get("observations", []))

    limit_reason = "unknown"
    if state["iteration"] >= state["max_iterations"]:
        limit_reason = "max_iterations_reached"
    elif any(e.get("type") == "security_violation" for e in state.get("errors", [])):
        limit_reason = "security_violation"

    observations.append({
        "type": "limit_reached",
        "reason": limit_reason,
        "iterations": state["iteration"],
    })

    return {
        **state,
        "success": False,
        "observations": observations,
        "final_result": {
            "limit_reason": limit_reason,
            "code": state.get("code"),
        },
    }


# ============================================================================
# GRAPH CONSTRUCTION
# ============================================================================

def compile_coding_subgraph():
    """Assemble le CodingSubgraph compilé (standard §5 : compile_<name>_subgraph)."""
    workflow = StateGraph(CodingState)

    workflow.add_node("analyze_task", analyze_task)
    workflow.add_node("execute_action", execute_action)
    workflow.add_node("evaluate", evaluate)
    workflow.add_node("generate_learning_signals", generate_learning_signals)
    workflow.add_node("finalize", finalize)
    workflow.add_node("finalize_with_limit", finalize_with_limit)

    workflow.add_edge(START, "analyze_task")
    workflow.add_edge("analyze_task", "execute_action")
    workflow.add_conditional_edges(
        "execute_action",
        should_continue,
        {
            "finalize": "finalize",
            "finalize_with_limit": "finalize_with_limit",
            "continue_debug": "evaluate",
        },
    )

    workflow.add_edge("evaluate", "generate_learning_signals")
    workflow.add_conditional_edges(
        "generate_learning_signals",
        should_continue,
        {
            "finalize": "finalize",
            "finalize_with_limit": "finalize_with_limit",
            "continue_debug": "execute_action",
        },
    )

    workflow.add_edge("finalize", END)
    workflow.add_edge("finalize_with_limit", END)

    return workflow.compile()


# Instance singleton
_coding_subgraph = None


def get_coding_subgraph():
    """Obtient l'instance compilée du CodingSubgraph (cache module)."""
    global _coding_subgraph
    if _coding_subgraph is None:
        _coding_subgraph = compile_coding_subgraph()
    return _coding_subgraph


async def run_coding_workflow(
    request: str,
    user_id: str,
    thread_id: str,
    language: Optional[str] = None,
    code: Optional[str] = None,
    max_iterations: int = 5,
) -> CodingResult:
    """Exécute le workflow de codage (contrat interne CodingResult)."""
    initial_state: CodingState = {
        "request": request,
        "language": language,
        "task_type": None,
        "code": code,
        "files": [],
        "errors": [],
        "test_results": [],
        "observations": [],
        "iteration": 0,
        "max_iterations": max_iterations,
        "success": False,
        "final_result": None,
        "user_id": user_id,
        "thread_id": thread_id,
    }

    subgraph = get_coding_subgraph()
    result_state = await subgraph.ainvoke(initial_state)

    learning_signals = []
    for obs in result_state.get("observations", []):
        if obs.get("type") == "learning_signals":
            learning_signals = obs.get("data", {}).get("signals", [])
            break

    return CodingResult(
        success=result_state["success"],
        status="success" if result_state["success"] else (
            "max_iterations" if result_state.get("final_result", {}).get("limit_reason") == "max_iterations_reached"
            else "security_violation" if result_state.get("final_result", {}).get("limit_reason") == "security_violation"
            else "failed"
        ),
        result=result_state.get("final_result", {}),
        observations=result_state.get("observations", []),
        errors=result_state.get("errors", []),
        code=result_state.get("code"),
        test_results=result_state.get("test_results"),
        learning_signals=learning_signals,
    )


__all__ = [
    "CodingState",
    "CodingResult",
    "analyze_task",
    "execute_action",
    "evaluate",
    "generate_learning_signals",
    "should_continue",
    "finalize",
    "finalize_with_limit",
    "compile_coding_subgraph",
    "get_coding_subgraph",
    "run_coding_workflow",
]