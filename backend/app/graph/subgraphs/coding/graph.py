"""
CodingSubgraph - Workflow spécialisé pour les tâches de codage.

Architecture:
START
  ↓
analyze_task (comprendre la demande)
  ↓
prepare_workspace (charger contexte, fichiers)
  ↓
generate_or_edit_code (écriture/modification)
  ↓
run_tests (validation)
  ├─ pass → evaluate
  └─ fail → debug_loop (max_iterations)
       ↓
  diagnose_error → modify_code → run_tests
       ↓
evaluate (qualité, tests, style)
  ↓
LearningObservation (vers Learning Engine)
  ↓
CodingResult
  ↓
END

États:
- request: str
- language: str | None
- task_type: str | None (write, edit, debug, explain, test)
- code: str | None
- files: list[dict]
- errors: list[dict]
- test_results: list[dict]
- observations: list[dict]
- iteration: int
- max_iterations: int
- success: bool
- final_result: dict | None
"""

from typing import TypedDict, List, Dict, Any, Optional, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from pydantic import BaseModel, Field
import time

from app.agent.tools.coding.tools import get_coding_tools, execute_code_tool, analyze_code_tool, explain_error_tool
from app.services.sandbox.executor import execute_code
from app.learning.engine import decide
from app.learning.decision import LearningDecision, LearningAction
from app.observability.langsmith_client import traceable_agent_action


# ============================================================================
# STATE & RESULT
# ============================================================================

class CodingState(TypedDict):
    """État interne du CodingSubgraph."""
    request: str
    language: Optional[str]
    task_type: Optional[str]  # write, edit, debug, explain, test
    code: Optional[str]
    files: List[Dict[str, Any]]
    errors: List[Dict[str, Any]]
    test_results: List[Dict[str, Any]]
    observations: List[Dict[str, Any]]
    iteration: int
    max_iterations: int
    success: bool
    final_result: Optional[Dict[str, Any]]
    user_id: Optional[str]
    thread_id: Optional[str]


class CodingResult(BaseModel):
    """Résultat structuré du CodingSubgraph."""
    success: bool
    status: str  # success, failed, timeout, security_violation, max_iterations
    result: Dict[str, Any] = Field(default_factory=dict)
    observations: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    code: Optional[str] = None
    test_results: Optional[List[Dict[str, Any]]] = None
    learning_signals: List[Dict[str, Any]] = Field(default_factory=list)


# ============================================================================
# NODES
# ============================================================================

@traceable_agent_action(name="coding_analyze_task", run_type="chain")
def analyze_task(state: CodingState) -> CodingState:
    """Analyse la demande de codage pour identifier le type de tâche."""
    request_lower = state["request"].lower()
    
    # Détection du type de tâche
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
    
    # Détection du langage
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
def execute_action(state: CodingState) -> CodingState:
    """Exécute l'action de codage (write/debug/test/explain)."""
    task_type = state["task_type"]
    request = state["request"]
    
    errors = list(state.get("errors", []))
    observations = list(state.get("observations", []))
    test_results = list(state.get("test_results", []))
    
    try:
        if task_type == "debug":
            # Utiliser explain_error pour diagnostiquer
            result = explain_error_tool.invoke({
                "code": state.get("code", ""),
                "error_message": request,
                "error_type": None,
            })
            
            if result.success and result.data:
                observations.append({
                    "type": "diagnosis",
                    "data": result.data,
                })
            else:
                errors.append({"type": "diagnosis_failed", "message": result.error})
        
        elif task_type == "test":
            # Exécuter le code avec tests
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
            # Pour write/edit, on utilise l'agent conversationnel via le Main Graph
            # Ici on prépare juste le contexte
            observations.append({
                "type": "action_prepared",
                "task_type": task_type,
                "ready_for_code_generation": True,
            })
        
        elif task_type == "explain":
            # Analyser le code pour explication
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
def evaluate(state: CodingState) -> CodingState:
    """Évalue le résultat du code (tests, qualité, conformité)."""
    observations = list(state.get("observations", []))
    
    test_results = state.get("test_results", [])
    errors = state.get("errors", [])
    
    # Évaluation basée sur les résultats de tests
    all_tests_passed = all(r.get("success", False) for r in test_results) if test_results else False
    has_errors = len(errors) > 0
    
    evaluation = {
        "tests_passed": all_tests_passed,
        "tests_count": len(test_results),
        "has_errors": has_errors,
        "errors_count": len(errors),
        "quality_score": 0.0,
    }
    
    # Score de qualité basique
    if all_tests_passed:
        evaluation["quality_score"] = 1.0
    elif has_errors:
        evaluation["quality_score"] = 0.0
    else:
        evaluation["quality_score"] = 0.5  # Tests non exécutés mais pas d'erreurs
    
    observations.append({
        "type": "evaluation",
        "data": evaluation,
    })
    
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
def generate_learning_signals(state: CodingState) -> CodingState:
    """Génère des signaux d'apprentissage pour le Learning Engine."""
    observations = list(state.get("observations", []))
    
    learning_signals = []
    
    # Signal basé sur le succès/échec
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
    
    # Signal basé sur les itérations
    if state["iteration"] > 3:
        learning_signals.append({
            "type": "multiple_attempts",
            "attempts": state["iteration"],
            "topic": state.get("topic", "unknown"),
        })
    
    observations.append({
        "type": "learning_signals",
        "data": {"signals": learning_signals},
    })
    
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
    
    # Continuer la boucle de debug
    return "continue_debug"


def finalize(state: CodingState) -> CodingState:
    """Finalise avec succès."""
    return {
        **state,
        "success": True,
    }


def finalize_with_limit(state: CodingState) -> CodingState:
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

def create_coding_subgraph():
    """Crée le graphe du CodingSubgraph."""
    
    workflow = StateGraph(CodingState)
    
    # Ajouter les nodes
    workflow.add_node("analyze_task", analyze_task)
    workflow.add_node("execute_action", execute_action)
    workflow.add_node("evaluate", evaluate)
    workflow.add_node("generate_learning_signals", generate_learning_signals)
    workflow.add_node("finalize", finalize)
    workflow.add_node("finalize_with_limit", finalize_with_limit)
    
    # edges
    workflow.add_edge(START, "analyze_task")
    workflow.add_edge("analyze_task", "execute_action")
    workflow.add_conditional_edges(
        "execute_action",
        should_continue,
        {
            "finalize": "finalize",
            "finalize_with_limit": "finalize_with_limit",
            "continue_debug": "evaluate",
        }
    )
    
    workflow.add_edge("evaluate", "generate_learning_signals")
    workflow.add_conditional_edges(
        "generate_learning_signals",
        should_continue,
        {
            "finalize": "finalize",
            "finalize_with_limit": "finalize_with_limit",
            "continue_debug": "execute_action",
        }
    )
    
    workflow.add_edge("finalize", END)
    workflow.add_edge("finalize_with_limit", END)
    
    return workflow.compile()


# Instance singleton
_coding_subgraph = None


def get_coding_subgraph():
    """Obtient l'instance du CodingSubgraph."""
    global _coding_subgraph
    if _coding_subgraph is None:
        _coding_subgraph = create_coding_subgraph()
    return _coding_subgraph


async def run_coding_workflow(
    request: str,
    user_id: str,
    thread_id: str,
    language: Optional[str] = None,
    code: Optional[str] = None,
    max_iterations: int = 5,
) -> CodingResult:
    """Exécute le workflow de codage."""
    
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
    
    # Extraire les learning signals
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
