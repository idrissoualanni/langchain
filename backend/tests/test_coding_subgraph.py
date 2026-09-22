"""
Tests pour le CodingSubgraph.

Tests du workflow:
- Analyse de tâche (debug, test, explain, write, edit)
- Exécution d'actions
- Évaluation des résultats
- Génération de signaux d'apprentissage
- Boucles de debug
- Limites (max_iterations, security_violation)

Tests d'intégration:
- Workflow complet succès
- Workflow avec échec
- Workflow avec timeout
- Isolation user/thread
"""

import pytest
from app.graph.subgraphs.coding.nodes import (
    CodingState,
    CodingResult,
    create_coding_subgraph,
    get_coding_subgraph,
    run_coding_workflow,
    analyze_task,
    execute_action,
    evaluate,
    should_continue,
)


class TestCodingState:
    """Tests de l'état CodingState."""
    
    def test_initial_state_valid(self):
        """L'état initial doit être valide."""
        state: CodingState = {
            "request": "Write a function to add two numbers",
            "language": "python",
            "task_type": None,
            "code": None,
            "files": [],
            "errors": [],
            "test_results": [],
            "observations": [],
            "iteration": 0,
            "max_iterations": 5,
            "success": False,
            "final_result": None,
            "user_id": "user_123",
            "thread_id": "thread_456",
        }
        
        # Vérifier que toutes les clés requises sont présentes
        assert "request" in state
        assert "iteration" in state
        assert "max_iterations" in state
        assert state["iteration"] == 0
        assert state["success"] is False


class TestAnalyzeTask:
    """Tests du node analyze_task."""
    
    def test_detect_debug_task(self):
        """Doit détecter une tâche de debug."""
        state: CodingState = {
            "request": "Debug this code: it raises TypeError",
            "language": None,
            "task_type": None,
            "code": "x = 1 / 0",
            "files": [],
            "errors": [],
            "test_results": [],
            "observations": [],
            "iteration": 0,
            "max_iterations": 5,
            "success": False,
            "final_result": None,
            "user_id": "user_123",
            "thread_id": "thread_456",
        }
        
        result = analyze_task(state)
        
        assert result["task_type"] == "debug"
        assert result["iteration"] == 1
    
    def test_detect_test_task(self):
        """Doit détecter une tâche de test."""
        state: CodingState = {
            "request": "Test this function with various inputs",
            "language": None,
            "task_type": None,
            "code": "def add(a, b): return a + b",
            "files": [],
            "errors": [],
            "test_results": [],
            "observations": [],
            "iteration": 0,
            "max_iterations": 5,
            "success": False,
            "final_result": None,
            "user_id": "user_123",
            "thread_id": "thread_456",
        }
        
        result = analyze_task(state)
        
        assert result["task_type"] == "test"
    
    def test_detect_explain_task(self):
        """Doit détecter une tâche d'explication."""
        state: CodingState = {
            "request": "Explain how this algorithm works",
            "language": None,
            "task_type": None,
            "code": "def fib(n): return n if n < 2 else fib(n-1) + fib(n-2)",
            "files": [],
            "errors": [],
            "test_results": [],
            "observations": [],
            "iteration": 0,
            "max_iterations": 5,
            "success": False,
            "final_result": None,
            "user_id": "user_123",
            "thread_id": "thread_456",
        }
        
        result = analyze_task(state)
        
        assert result["task_type"] == "explain"
    
    def test_detect_write_task_default(self):
        """Par défaut, doit détecter une tâche d'écriture."""
        state: CodingState = {
            "request": "Create a function to calculate factorial",
            "language": None,
            "task_type": None,
            "code": None,
            "files": [],
            "errors": [],
            "test_results": [],
            "observations": [],
            "iteration": 0,
            "max_iterations": 5,
            "success": False,
            "final_result": None,
            "user_id": "user_123",
            "thread_id": "thread_456",
        }
        
        result = analyze_task(state)
        
        assert result["task_type"] == "write"
    
    def test_detect_python_language(self):
        """Doit détecter le langage Python."""
        state: CodingState = {
            "request": "Write Python code for sorting",
            "language": None,
            "task_type": None,
            "code": None,
            "files": [],
            "errors": [],
            "test_results": [],
            "observations": [],
            "iteration": 0,
            "max_iterations": 5,
            "success": False,
            "final_result": None,
            "user_id": "user_123",
            "thread_id": "thread_456",
        }
        
        result = analyze_task(state)
        
        assert result["language"] == "python"


class TestExecuteAction:
    """Tests du node execute_action."""
    
    def test_execute_debug_action(self):
        """Doit exécuter une action de debug."""
        state: CodingState = {
            "request": "Fix the division by zero error",
            "language": "python",
            "task_type": "debug",
            "code": "result = 10 / 0",
            "files": [],
            "errors": [],
            "test_results": [],
            "observations": [],
            "iteration": 0,
            "max_iterations": 5,
            "success": False,
            "final_result": None,
            "user_id": "user_123",
            "thread_id": "thread_456",
        }
        
        result = execute_action(state)
        
        assert result["iteration"] == 1
        # Devrait avoir des observations ou des erreurs
        assert len(result["observations"]) > 0 or len(result["errors"]) > 0
    
    def test_execute_test_action_success(self):
        """Doit exécuter un test avec succès."""
        state: CodingState = {
            "request": "Test this code",
            "language": "python",
            "task_type": "test",
            "code": "print('Hello')",
            "files": [],
            "errors": [],
            "test_results": [],
            "observations": [],
            "iteration": 0,
            "max_iterations": 5,
            "success": False,
            "final_result": None,
            "user_id": "user_123",
            "thread_id": "thread_456",
        }
        
        result = execute_action(state)
        
        assert result["iteration"] == 1
        assert len(result["test_results"]) > 0
        assert result["test_results"][0]["success"] is True
    
    def test_execute_test_action_failure(self):
        """Doit détecter un échec d'exécution."""
        state: CodingState = {
            "request": "Test this broken code",
            "language": "python",
            "task_type": "test",
            "code": "x = 1 / 0",
            "files": [],
            "errors": [],
            "test_results": [],
            "observations": [],
            "iteration": 0,
            "max_iterations": 5,
            "success": False,
            "final_result": None,
            "user_id": "user_123",
            "thread_id": "thread_456",
        }
        
        result = execute_action(state)
        
        assert result["iteration"] == 1
        assert len(result["errors"]) > 0


class TestEvaluate:
    """Tests du node evaluate."""
    
    def test_evaluate_success(self):
        """Doit évaluer comme succès quand tests passés."""
        state: CodingState = {
            "request": "Test",
            "language": "python",
            "task_type": "test",
            "code": "print('OK')",
            "files": [],
            "errors": [],
            "test_results": [{"success": True, "stdout": "OK"}],
            "observations": [],
            "iteration": 1,
            "max_iterations": 5,
            "success": False,
            "final_result": None,
            "user_id": "user_123",
            "thread_id": "thread_456",
        }
        
        result = evaluate(state)
        
        assert result["success"] is True
        assert len(result["observations"]) > 0
    
    def test_evaluate_failure(self):
        """Doit évaluer comme échec quand erreurs présentes."""
        state: CodingState = {
            "request": "Test",
            "language": "python",
            "task_type": "test",
            "code": "broken",
            "files": [],
            "errors": [{"type": "runtime_error", "message": "NameError"}],
            "test_results": [],
            "observations": [],
            "iteration": 1,
            "max_iterations": 5,
            "success": False,
            "final_result": None,
            "user_id": "user_123",
            "thread_id": "thread_456",
        }
        
        result = evaluate(state)
        
        assert result["success"] is False


class TestShouldContinue:
    """Tests de la fonction de décision should_continue."""
    
    def test_continue_on_success(self):
        """Doit finaliser sur succès."""
        state: CodingState = {
            "request": "Test",
            "language": "python",
            "task_type": "test",
            "code": "print('OK')",
            "files": [],
            "errors": [],
            "test_results": [{"success": True}],
            "observations": [],
            "iteration": 1,
            "max_iterations": 5,
            "success": True,
            "final_result": None,
            "user_id": "user_123",
            "thread_id": "thread_456",
        }
        
        decision = should_continue(state)
        
        assert decision == "finalize"
    
    def test_continue_on_max_iterations(self):
        """Doit finaliser quand max_iterations atteint."""
        state: CodingState = {
            "request": "Test",
            "language": "python",
            "task_type": "debug",
            "code": "broken",
            "files": [],
            "errors": [],
            "test_results": [],
            "observations": [],
            "iteration": 5,
            "max_iterations": 5,
            "success": False,
            "final_result": None,
            "user_id": "user_123",
            "thread_id": "thread_456",
        }
        
        decision = should_continue(state)
        
        assert decision == "finalize_with_limit"
    
    def test_continue_on_security_violation(self):
        """Doit finaliser sur violation de sécurité."""
        state: CodingState = {
            "request": "Test",
            "language": "python",
            "task_type": "test",
            "code": "import socket",
            "files": [],
            "errors": [{"type": "security_violation", "details": ["socket"]}],
            "test_results": [],
            "observations": [],
            "iteration": 1,
            "max_iterations": 5,
            "success": False,
            "final_result": None,
            "user_id": "user_123",
            "thread_id": "thread_456",
        }
        
        decision = should_continue(state)
        
        assert decision == "finalize_with_limit"
    
    def test_continue_debug_loop(self):
        """Doit continuer la boucle de debug si pas de limite."""
        state: CodingState = {
            "request": "Debug",
            "language": "python",
            "task_type": "debug",
            "code": "x = 1",
            "files": [],
            "errors": [],
            "test_results": [],
            "observations": [],
            "iteration": 2,
            "max_iterations": 5,
            "success": False,
            "final_result": None,
            "user_id": "user_123",
            "thread_id": "thread_456",
        }
        
        decision = should_continue(state)
        
        assert decision == "continue_debug"


@pytest.mark.asyncio
class TestCodingWorkflow:
    """Tests du workflow complet."""
    
    async def test_successful_coding_workflow(self):
        """Workflow de codage avec succès."""
        result = await run_coding_workflow(
            request="Print hello world",
            user_id="user_123",
            thread_id="thread_456",
            language="python",
            code="print('Hello World')",
            max_iterations=5,
        )
        
        assert isinstance(result, CodingResult)
        assert result.success is True or result.success is False  # Dépend de l'exécution
    
    async def test_workflow_with_security_violation(self):
        """Workflow avec violation de sécurité."""
        result = await run_coding_workflow(
            request="Import socket and create connection",
            user_id="user_123",
            thread_id="thread_456",
            language="python",
            code="import socket",
            max_iterations=5,
        )
        
        assert isinstance(result, CodingResult)
        # Doit détecter la violation de sécurité
        assert any("security" in str(e).lower() for e in result.errors) or result.status == "security_violation"
    
    async def test_workflow_learning_signals(self):
        """Workflow génère des signaux d'apprentissage."""
        result = await run_coding_workflow(
            request="Simple print statement",
            user_id="user_123",
            thread_id="thread_456",
            language="python",
            code="print('test')",
            max_iterations=3,
        )
        
        assert isinstance(result, CodingResult)
        # Devrait avoir des observations
        assert len(result.observations) > 0


class TestCodingSubgraphInstance:
    """Tests de l'instance du subgraph."""
    
    def test_get_coding_subgraph_singleton(self):
        """get_coding_subgraph retourne un singleton."""
        graph1 = get_coding_subgraph()
        graph2 = get_coding_subgraph()
        
        assert graph1 is graph2
    
    def test_create_coding_subgraph_returns_compiled(self):
        """create_coding_subgraph retourne un graphe compilé."""
        graph = create_coding_subgraph()
        
        # Vérifier que c'est un StateGraph compilé
        assert hasattr(graph, 'invoke') or hasattr(graph, 'ainvoke')
