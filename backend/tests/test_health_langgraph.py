"""Reproduction : /api/health déclarait `langgraph: true` en dur.

Le workflow de déploiement attend `"langgraph":true` pour valider staging
et production : un agent dont l'initialisation a échoué (AGENT_INIT_ERROR)
passait quand même la vérification.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    import app.api.health as health_api
    from app.main import app

    monkeypatch.setattr(health_api, "check_ollama_health", lambda: True)
    monkeypatch.setattr(health_api, "check_database_health", lambda: True)
    return TestClient(app)


@pytest.mark.parametrize("agent, expected", [(None, False), (object(), True)])
def test_health_reflete_l_etat_reel_de_l_agent(client, monkeypatch, agent, expected):
    import app.graph.main.graph as graph

    monkeypatch.setattr(graph, "_agent", agent)

    data = client.get("/api/health").json()

    assert data["langgraph"] is expected
    assert data["status"] == ("ok" if expected else "degraded")
