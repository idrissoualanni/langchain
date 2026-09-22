"""
MODEL GATEWAY WIRING TESTS (mission §1-§7)

Tests pour :
- Registry → Resolver : résolution de modèle par purpose, déterministe,
  tracée (reason), jamais de modèle désactivé/sans capacité
- Gateway : instanciation UNIQUE (ChatOllama jamais en dur dans le
  graph), aucun secret exposé, erreurs contrôlées (ModelGatewayError)
- Limites agentiques configurables (recursion_limit, timeout, retries)
- Retries bornés réservés aux erreurs transitoires
- Gate de capabilities du workflow router (coding/research→tools,
  video→vision)
"""

import os
import sys

import pytest


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture(autouse=True)
def _clean_purpose_env(monkeypatch):
    """Les tests de résolution doivent être déterministes : purge de
    tous les env <PURPOSE>_MODEL_ID qui pourraient pointer vers un
    modèle qui n'existe pas dans le registry de test."""
    from app.services.models.resolver import set_global_assignment
    from app.services.models.resolver import _global_assignments

    _global_assignments.clear()
    for purpose in ("DEFAULT", "CODING", "RESEARCH", "FAST", "REASONING", "VISION"):
        monkeypatch.delenv(f"{purpose}_MODEL_ID", raising=False)
    yield


# ============================================================
# RESOLVER (registry → resolver)
# ============================================================

class TestResolver:
    def test_default_model_is_resolved_enabled(self):
        """Le modèle défaut (registry models.yaml) est résolu et enabled."""
        from app.services.models.resolver import resolve_model_for_purpose

        result = resolve_model_for_purpose("default")
        assert result.is_enabled is True
        assert result.config is not None
        assert result.config.enabled is True
        assert result.reason

    def test_default_model_supports_tools(self):
        """Le modèle défaut du registry supporte les tools (gate §4)."""
        from app.services.models.resolver import resolve_model_for_purpose

        result = resolve_model_for_purpose("default")
        assert result.config.capabilities.supports_tools is True

    def test_capability_mismatch_disables_purpose(self):
        """Un modèle SANS vision ne peut pas satisfaire purpose='vision'
        → is_enabled=False + reason explicite (jamais de config bidon)."""
        from app.services.models.resolver import resolve_model_for_purpose

        result = resolve_model_for_purpose("default", required_capabilities=["vision"])
        assert result.is_enabled is False
        assert "sans capacités requises" in result.reason
        assert result.config is not None

    def test_disabled_model_never_selected(self):
        """Un modèle désactivé n'est JAMAIS sélectionnable, même en
        assignment global explicite → repli défaut tracé."""
        from app.services.models.resolver import resolve_model_for_purpose, set_global_assignment

        set_global_assignment("fast", "disabled-test-model")
        result = resolve_model_for_purpose("fast")
        assert result.is_enabled is True
        assert result.config.id == "default"
        assert result.resolved_from == "fallback"

    def test_unknown_purpose_falls_back_to_default(self):
        """Purpose inconnu → repli déterministe sur le défaut (traçé)."""
        from app.services.models.resolver import resolve_model_for_purpose

        result = resolve_model_for_purpose("workflow-bogus")
        assert result.is_enabled is True
        assert result.resolved_from == "fallback"
        assert result.config is not None

    def test_supported_purposes_taxonomy(self):
        """La taxonomie des purposes est exactement celle du contrat."""
        from app.services.models.resolver import SUPPORTED_PURPOSES

        assert SUPPORTED_PURPOSES == (
            "default", "coding", "research", "fast", "reasoning", "vision",
        )

    def test_required_capabilities_mapping(self):
        """coding/research exigent tools, vision exige vision (§4)."""
        from app.services.models.resolver import required_capabilities_for_purpose

        assert required_capabilities_for_purpose("coding") == ["tools"]
        assert required_capabilities_for_purpose("research") == ["tools"]
        assert required_capabilities_for_purpose("vision") == ["vision"]
        assert required_capabilities_for_purpose("default") is None

    def test_get_model_for_subgraph_maps_purposes(self):
        """Le mapping subgraph → purpose suit le contrat."""
        from app.services.models.resolver import (
            _CAPABILITIES_FOR_PURPOSE,
            required_capabilities_for_purpose,
        )

        for purpose, caps in _CAPABILITIES_FOR_PURPOSE.items():
            assert required_capabilities_for_purpose(purpose) == caps


# ============================================================
# GATEWAY (provider + instanciation unique)
# ============================================================

class TestGateway:
    def test_get_llm_for_purpose_returns_chat_model(self):
        """Le gateway instancie LE LLM du modèle résolu (ChatOllama
        pour le provider ollama — plus AUCUN ChatOllama dans le graph)."""
        from app.services.models.gateway import get_llm_for_purpose

        llm = get_llm_for_purpose("default")
        assert llm is not None
        assert llm.model == "gemma4:31b-cloud"

    def test_create_llm_from_config_disabled_raises(self):
        """create_llm_from_config sur un modèle désactivé → erreur
        contrôlée (le champ enabled est RESPECTÉ au point d'usage)."""
        from app.services.models.gateway import ModelGatewayError, create_llm_from_config

        with pytest.raises(ModelGatewayError):
            create_llm_from_config("disabled-test-model")

    def test_create_llm_from_config_unknown_raises(self):
        """Modèle inconnu → ModelGatewayError (jamais de config bidon)."""
        from app.services.models.gateway import ModelGatewayError, create_llm_from_config

        with pytest.raises(ModelGatewayError):
            create_llm_from_config("model-inconnu")

    def test_gateway_error_is_controlled_runtime_error(self):
        from app.services.models.gateway import ModelGatewayError

        assert issubclass(ModelGatewayError, RuntimeError)

    def test_no_secret_placeholder_in_gateway(self):
        """Le placeholder sk-litellm-placeholder a été supprimé ; le
        gateway n'expose AUCUNE valeur de clé dans son code."""
        from app.services.models import gateway

        source = sys.modules[gateway.__name__].__file__
        with open(source, encoding="utf-8") as f:
            content = f.read()

        assert "sk-litellm-placeholder" not in content
        assert "placeholder" not in content
        assert "sk-ant-" not in content

    def test_no_catch_all_no_silent_fallback(self):
        """Pas de fallback silencieux : un provider inconnu lève une
        erreur contrôlée (ModelGatewayError) — jamais un ChatOllama
        en dur avec un provider étranger."""
        from app.services.models.gateway import ModelGatewayError, _get_direct_llm
        from app.services.models.registry import get_model_config

        config = get_model_config("default")
        config.provider = "provider-inconnu"
        with pytest.raises(ModelGatewayError):
            _get_direct_llm(config)


# ============================================================
# LIMITES AGENTIQUES CONFIGURABLES (§3)
# ============================================================

class TestLimits:
    def test_recursion_limit_env_driven(self, monkeypatch):
        """AGENT_RECURSION_LIMIT est lisible depuis l'environnement."""
        monkeypatch.setenv("AGENT_RECURSION_LIMIT", "42")
        import importlib

        import app.config as config

        importlib.reload(config)
        try:
            assert config.AGENT_RECURSION_LIMIT == 42
        finally:
            importlib.reload(config)

    def test_recursion_limit_positive(self):
        from app.config import AGENT_RECURSION_LIMIT

        assert isinstance(AGENT_RECURSION_LIMIT, int)
        assert AGENT_RECURSION_LIMIT > 0

    def test_agent_timeout_configurable(self, monkeypatch):
        monkeypatch.setenv("AGENT_TIMEOUT_SECONDS", "30")
        import importlib

        import app.config as config

        importlib.reload(config)
        try:
            assert config.AGENT_TIMEOUT_SECONDS == 30
        finally:
            importlib.reload(config)

    def test_runner_config_includes_recursion_limit(self):
        """La config d'invocation du runner porte TOUJOURS la borne
        recursion_limit (voie LangGraph officielle, mission §3)."""
        from app.services.agent.runner import _config_for
        from app.config import AGENT_RECURSION_LIMIT

        config = _config_for("thread-42", user_id="user-1")
        assert config["recursion_limit"] == AGENT_RECURSION_LIMIT
        assert config["configurable"]["thread_id"] == "thread-42"
        assert config["configurable"]["user_id"] == "user-1"

    def test_max_iterations_bounded_by_env(self, monkeypatch):
        """AGENT_MAX_ITERATIONS/TOOL_CALLS bornent la boucle agentique
        (et alimentent le recurrence_limit par défaut)."""
        monkeypatch.setenv("AGENT_MAX_ITERATIONS", "5")
        monkeypatch.setenv("AGENT_MAX_TOOL_CALLS", "4")
        import importlib

        import app.config as config

        importlib.reload(config)
        try:
            assert config.AGENT_MAX_ITERATIONS == 5
            assert config.AGENT_MAX_TOOL_CALLS == 4
            assert config.AGENT_RECURSION_LIMIT >= max(5, 4) * 3 + 40
        finally:
            importlib.reload(config)

    def test_graph_uses_retry_policy_on_agent_node(self):
        """Le node AGENT du Main Graph est poli (retry borné sur
        erreurs transitoires). Le timeout n'est PAS passé au node
        (sync, langgraph 1.2.11) — il est ENFORCÉ par le runner
        (AGENT_TIMEOUT_SECONDS via wait_for, I/O boundary)."""
        import inspect

        from app.agent import runner
        from app.graph.main import compile_main_graph

        source = inspect.getsource(compile_main_graph)
        assert "retry_policy=" in source
        assert "timeout=AGENT_TIMEOUT_SECONDS" not in source
        assert "is_transient_error" in source

        runner_source = inspect.getsource(runner)
        assert "AGENT_TIMEOUT_SECONDS" in runner_source
        assert "invoke_llm_with_retry" in runner_source


# ============================================================
# RETRIES BORNÉS (mission §14)
# ============================================================

class TestRetryBounded:
    def test_timeout_is_transient(self):
        from app.services.models.retry import is_transient_error

        assert is_transient_error(TimeoutError()) is True
        assert is_transient_error(ConnectionError()) is True

    def test_status_code_classification(self):
        from app.services.models.retry import is_transient_error

        class _Http:
            def __init__(self, status):
                self.status_code = status

        assert is_transient_error(_Http(429)) is True
        assert is_transient_error(_Http(503)) is True
        assert is_transient_error(_Http(502)) is True
        assert is_transient_error(_Http(500)) is True
        assert is_transient_error(_Http(400)) is False
        assert is_transient_error(_Http(401)) is False
        assert is_transient_error(_Http(403)) is False
        assert is_transient_error(_Http(404)) is False

    def test_validation_error_never_retried(self):
        """Validation/authorization → NON-transitoire (pas de retry)."""
        from app.services.models.retry import is_transient_error

        assert is_transient_error(ValueError("message invalide")) is False
        assert is_transient_error(TypeError("signature invalide")) is False
        assert is_transient_error(KeyError("champ manquant")) is False

    def test_sync_retry_never_retries_non_transient(self):
        """max_attempts borné : une erreur NON transitoire ne déclenche
        AUCUN retry (1 seul appel puis relève)."""
        from app.services.models.retry import invoke_llm_with_retry_sync

        calls = []

        def _boom():
            calls.append(1)
            raise ValueError("invalide")

        with pytest.raises(ValueError):
            invoke_llm_with_retry_sync(
                _boom, max_attempts=3, timeout_seconds=5
            )
        assert len(calls) == 1

    def test_sync_retry_bounded_to_max_attempts(self):
        """Erreur transitoire → retries bornés exactement à max_attempts."""
        from app.services.models.retry import invoke_llm_with_retry_sync

        calls = []

        def _boom():
            calls.append(1)
            raise ConnectionError("réseau indisponible")

        with pytest.raises(ConnectionError):
            invoke_llm_with_retry_sync(
                _boom, max_attempts=2, timeout_seconds=5
            )
        assert len(calls) == 2


# ============================================================
# GATE DE CAPABILITIES — WORKFLOW ROUTER (§4)
# ============================================================

class TestCapabilityGate:
    def test_main_has_no_gate(self):
        """Le workflow 'main' (chaîne principale) n'exige aucune
        capacité → pas de gate."""
        from app.graph.nodes.workflow_router import _capability_gate_reason

        assert _capability_gate_reason("main") is None

    def test_activity_has_no_gate(self):
        from app.graph.nodes.workflow_router import _capability_gate_reason

        assert _capability_gate_reason("activity") is None

    def test_coding_gate_passes_when_tools_supported(self):
        """coding requiert tools ; le modèle défaut supporte tools →
        aucune raison de blocage."""
        from app.graph.nodes.workflow_router import _capability_gate_reason

        assert _capability_gate_reason("coding") is None

    def test_video_gate_blocks_when_no_vision_model(self):
        """video requiert vision ; le modèle défaut du registry ne
        supporte PAS vision → gate bloque (raison explicite)."""
        from app.graph.nodes.workflow_router import _capability_gate_reason

        reason = _capability_gate_reason("video")
        assert reason is not None

    def test_unwired_workflow_routes_to_context(self):
        """Workflow non câblé → repli documenté sur la chaîne principale."""
        from app.graph.nodes.workflow_router import route_after_workflow_router

        target = route_after_workflow_router({"workflow": {"workflow": "video"}})
        assert target == "context"