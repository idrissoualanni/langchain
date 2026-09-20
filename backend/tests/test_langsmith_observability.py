"""
LANGSMITH OBSERVABILITY TESTS

Tests pour la couche d'observabilité LangSmith.
Vérifie le tracing, le monitoring et l'intégration avec LangGraph/LangChain.
"""

import pytest
import os
from unittest.mock import patch, MagicMock


class TestLangSmithClient:
    """Tests du client LangSmith."""
    
    def test_langsmith_client_creation(self):
        """Le client LangSmith peut être instancié."""
        from app.observability.langsmith_client import LangSmithClient
        
        with patch.dict(os.environ, {
            "LANGSMITH_ENABLED": "true",
            "LANGSMITH_API_KEY": "test_key",
            "LANGSMITH_ENDPOINT": "https://api.smith.langchain.com",
            "LANGSMITH_PROJECT": "test-project",
            "LANGSMITH_ENVIRONMENT": "test",
        }, clear=False):
            client = LangSmithClient()
            assert client is not None
    
    def test_langsmith_disabled_when_no_api_key(self):
        """Le client est désactivé sans API key."""
        from app.observability.langsmith_client import LangSmithClient
        
        with patch.dict(os.environ, {
            "LANGSMITH_ENABLED": "true",
            "LANGSMITH_API_KEY": "",
        }, clear=False):
            client = LangSmithClient()
            assert not client.is_enabled()
    
    def test_langsmith_enabled_with_api_key(self):
        """Le client est activé avec une API key."""
        from app.observability.langsmith_client import LangSmithClient
        
        with patch.dict(os.environ, {
            "LANGSMITH_ENABLED": "true",
            "LANGSMITH_API_KEY": "test_key",
        }, clear=False):
            client = LangSmithClient()
            # Le client est créé mais peut échouer à la connexion
            # is_enabled() retourne True si configuré
            assert client.enabled  # Configuration OK
    
    def test_langsmith_disabled_by_env(self):
        """Le client peut être désactivé par variable d'environnement."""
        from app.observability.langsmith_client import LangSmithClient
        
        with patch.dict(os.environ, {
            "LANGSMITH_ENABLED": "false",
            "LANGSMITH_API_KEY": "test_key",
        }, clear=False):
            client = LangSmithClient()
            assert not client.enabled


class TestLangSmithTracing:
    """Tests des fonctions de tracing."""
    
    def test_get_langsmith_client(self):
        """La fonction get_langsmith_client retourne un singleton."""
        from app.observability.langsmith_client import (
            get_langsmith_client,
            langsmith_client,
        )
        
        client = get_langsmith_client()
        assert client is langsmith_client
    
    def test_traceable_decorator_exists(self):
        """Le décorateur traceable_agent_action existe."""
        from app.observability.langsmith_client import traceable_agent_action
        
        assert callable(traceable_agent_action)
        
        # Test avec un mock
        with patch.dict(os.environ, {"LANGSMITH_ENABLED": "false"}, clear=False):
            @traceable_agent_action(name="test_action")
            def test_func():
                return "result"
            
            result = test_func()
            assert result == "result"


class TestLangSmithHealth:
    """Tests de l'endpoint health LangSmith."""
    
    def test_health_langsmith_endpoint_exists(self):
        """L'endpoint /api/health/langsmith existe."""
        from fastapi.testclient import TestClient
        from app.main import app
        
        client = TestClient(app)
        response = client.get("/api/health/langsmith")
        
        # Doit retourner 200 même si non configuré
        assert response.status_code == 200
        
        data = response.json()
        assert "enabled" in data
        assert "configured" in data
        assert "environment" in data
    
    def test_health_langsmith_structure(self):
        """La réponse health/langsmith a la bonne structure."""
        from fastapi.testclient import TestClient
        from app.main import app
        
        client = TestClient(app)
        response = client.get("/api/health/langsmith")
        
        data = response.json()
        
        # Champs obligatoires
        assert isinstance(data.get("enabled"), bool)
        assert isinstance(data.get("configured"), bool)
        assert "environment" in data
        assert "endpoint" in data
        assert "project" in data


class TestLangSmithNonBlocking:
    """Tests que LangSmith ne bloque pas l'application."""
    
    def test_app_works_without_langsmith(self):
        """L'application fonctionne sans LangSmith configuré."""
        from fastapi.testclient import TestClient
        from app.main import app
        
        # LangSmith n'est pas configuré dans l'environnement de test
        client = TestClient(app)
        
        # La santé générale doit être OK
        response = client.get("/api/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] in ["ok", "degraded"]
    
    def test_langsmith_error_does_not_crash_app(self):
        """Une erreur LangSmith ne fait pas planter l'application."""
        from app.observability.langsmith_client import (
            log_agent_observation,
            create_dataset,
            add_example_to_dataset,
        )
        
        # Ces fonctions ne doivent pas lever d'exception
        # même si LangSmith n'est pas configuré
        log_agent_observation(
            action="test",
            success=True,
            result={"key": "value"},
        )
        
        dataset_id = create_dataset("test_dataset")
        assert dataset_id is None  # Pas de dataset sans LangSmith
        
        success = add_example_to_dataset(
            dataset_id="test",
            inputs={"input": "test"},
        )
        assert success is False


class TestLangSmithMetadata:
    """Tests des métadonnées de trace."""
    
    def test_set_trace_metadata_function_exists(self):
        """La fonction set_trace_metadata existe."""
        from app.observability.langsmith_client import set_trace_metadata
        
        # Ne doit pas lever d'exception
        set_trace_metadata(
            user_id="user_123",
            thread_id="thread_456",
            run_id="run_789",
            model="gpt-4",
            workflow="coding",
        )
    
    def test_log_agent_observation_function_exists(self):
        """La fonction log_agent_observation existe."""
        from app.observability.langsmith_client import log_agent_observation
        
        # Ne doit pas lever d'exception
        log_agent_observation(
            action="tool_call",
            success=True,
            result={"output": "test"},
            duration_ms=100.0,
            tokens={"input": 10, "output": 20},
        )


class TestLangSmithEvaluation:
    """Tests des fonctionnalités d'évaluation."""
    
    def test_create_dataset_function_exists(self):
        """La fonction create_dataset existe."""
        from app.observability.langsmith_client import create_dataset
        
        # Retourne None si LangSmith n'est pas configuré
        dataset_id = create_dataset("test_dataset", "Test description")
        assert dataset_id is None
    
    def test_add_example_to_dataset_function_exists(self):
        """La fonction add_example_to_dataset existe."""
        from app.observability.langsmith_client import add_example_to_dataset
        
        # Retourne False si LangSmith n'est pas configuré
        success = add_example_to_dataset(
            dataset_id="test",
            inputs={"question": "test"},
            outputs={"answer": "test"},
        )
        assert success is False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
