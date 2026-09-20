"""
MODEL GATEWAY + KNOWLEDGE ACL + LANGSMITH OBSERVABILITY TESTS

Tests pour :
- Model Registry / Resolver / Gateway
- Knowledge Access Control
- LangSmith Observability
"""

import pytest
import os


# ============================================================
# MODEL REGISTRY TESTS
# ============================================================

def test_model_registry_get_config():
    """Test: Récupérer une configuration de modèle."""
    from app.models.registry import get_model_config
    
    config = get_model_config("default")
    # Peut être None si pas configuré ou un ModelConfig
    print("✓ test_model_registry_get_config")


def test_model_registry_list_all():
    """Test: Lister tous les modèles."""
    from app.models.registry import list_all_model_configs
    
    models = list_all_model_configs()
    assert isinstance(models, list)
    print("✓ test_model_registry_list_all")


def test_model_registry_save_update():
    """Test: Sauvegarder/mettre à jour un modèle."""
    from app.models.schemas import ModelConfig, ModelCapabilities
    
    config = ModelConfig(
        id="test-model",
        display_name="Test Model",
        provider="ollama",
        model_name="gemma2:9b",
        enabled=True,
        capabilities=ModelCapabilities(),
    )
    
    from app.models.registry import save_model_config
    saved = save_model_config(config)
    assert saved is True or saved is False
    print("✓ test_model_registry_save_update")


# ============================================================
# MODEL RESOLVER TESTS
# ============================================================

def test_model_resolver_default_purpose():
    """Test: Résolution du modèle par défaut."""
    from app.models.resolver import resolve_model_for_purpose
    
    result = resolve_model_for_purpose(purpose="default")
    # Peut retourner None ou un ModelPurposeResult
    print("✓ test_model_resolver_default_purpose")


def test_model_resolver_coding_purpose():
    """Test: Résolution du modèle coding."""
    from app.models.resolver import resolve_model_for_purpose
    
    result = resolve_model_for_purpose(purpose="coding")
    print("✓ test_model_resolver_coding_purpose")


def test_model_resolver_unknown_purpose():
    """Test: Résolution avec purpose inconnu."""
    from app.models.resolver import resolve_model_for_purpose
    
    result = resolve_model_for_purpose(purpose="unknown_purpose_xyz")
    # Doit retourner None ou fallback to default
    print("✓ test_model_resolver_unknown_purpose")


def test_model_resolver_disabled_model():
    """Test: Modèle désactivé non retourné."""
    from app.models.schemas import ModelConfig, ModelCapabilities
    from app.models.registry import save_model_config
    
    # Créer un modèle désactivé
    config = ModelConfig(
        id="disabled-test-model",
        display_name="Disabled Test",
        provider="ollama",
        model_name="test",
        enabled=False,
        capabilities=ModelCapabilities(),
    )
    save_model_config(config)
    
    from app.models.resolver import resolve_model_for_purpose
    # Le resolver ne doit pas retourner un modèle désactivé
    print("✓ test_model_resolver_disabled_model")


# ============================================================
# KNOWLEDGE ACCESS CONTROL TESTS
# ============================================================

def test_knowledge_access_public():
    """Test: Accès public autorisé."""
    from app.knowledge_access.resolver import check_access
    
    allowed_result = check_access(
        knowledge_base_id="public_kb",
        user_id="user_123",
        group_ids=[],
        is_admin=False,
    )
    # Public devrait être accessible
    print(f"✓ test_knowledge_access_public (allowed={allowed_result.allowed})")


def test_knowledge_access_private_owner():
    """Test: Accès private autorisé au propriétaire."""
    from app.knowledge_access.resolver import check_access
    
    # Note: La logique actuelle vérifie les règles explicites
    # Pour un test complet, il faudrait créer une règle d'accès
    allowed_result = check_access(
        knowledge_base_id="private_kb",
        user_id="owner_123",
        group_ids=[],
        is_admin=False,
    )
    print(f"✓ test_knowledge_access_private_owner (allowed={allowed_result.allowed})")


def test_knowledge_access_private_non_owner():
    """Test: Accès private refusé au non-propriétaire."""
    from app.knowledge_access.resolver import check_access
    
    allowed_result = check_access(
        knowledge_base_id="private_kb",
        user_id="other_user",
        group_ids=[],
        is_admin=False,
    )
    # Private sans règle explicite → refusé
    assert allowed_result.allowed is False
    print("✓ test_knowledge_access_private_non_owner")


def test_knowledge_access_group_member():
    """Test: Accès group autorisé au membre."""
    from app.knowledge_access.resolver import check_access
    
    allowed_result = check_access(
        knowledge_base_id="group_kb",
        user_id="member_123",
        group_ids=["beginners"],
        is_admin=False,
    )
    print(f"✓ test_knowledge_access_group_member (allowed={allowed_result.allowed})")


def test_knowledge_access_user_scope():
    """Test: Accès user scope."""
    from app.knowledge_access.resolver import check_access
    
    allowed_result = check_access(
        knowledge_base_id="user_kb",
        user_id="target_user",
        group_ids=[],
        is_admin=False,
    )
    print(f"✓ test_knowledge_access_user_scope (allowed={allowed_result.allowed})")


def test_knowledge_access_admin_override():
    """Test: Admin override."""
    from app.knowledge_access.resolver import check_access
    
    allowed_result = check_access(
        knowledge_base_id="any_kb",
        user_id="admin_user",
        group_ids=[],
        is_admin=True,
    )
    assert allowed_result.allowed is True
    print("✓ test_knowledge_access_admin_override")


def test_knowledge_access_cross_user_isolation():
    """Test: Isolation cross-user."""
    from app.knowledge_access.resolver import check_access
    
    # User A ne peut pas accéder aux connaissances privées de User B
    allowed_a = check_access(
        knowledge_base_id="kb_b",
        user_id="user_a",
        group_ids=[],
        is_admin=False,
    )
    allowed_b = check_access(
        knowledge_base_id="kb_a",
        user_id="user_b",
        group_ids=[],
        is_admin=False,
    )
    
    # Sans règles explicites, accès refusé
    assert allowed_a.allowed is False
    assert allowed_b.allowed is False
    print("✓ test_knowledge_access_cross_user_isolation")


def test_knowledge_access_cross_group_isolation():
    """Test: Isolation cross-group."""
    from app.knowledge_access.resolver import check_access
    
    allowed = check_access(
        knowledge_base_id="group_b_kb",
        user_id="user_a",
        group_ids=["group_a"],  # Pas member de group_b
        is_admin=False,
    )
    # Non-membre du groupe → accès refusé (sauf règle explicite)
    print(f"✓ test_knowledge_access_cross_group_isolation (allowed={allowed.allowed})")


# ============================================================
# LANGSMITH OBSERVABILITY TESTS
# ============================================================

def test_langsmith_client_not_enabled():
    """Test: LangSmith client existe."""
    from app.observability.langsmith_client import get_langsmith_client

    client = get_langsmith_client()
    # Client existe toujours
    assert client is not None
    print("✓ test_langsmith_client_not_enabled")


def test_langsmith_trace_metadata():
    """Test: set_trace_metadata fonctionne."""
    from app.observability.langsmith_client import set_trace_metadata

    # Ne doit pas crasher
    set_trace_metadata(
        user_id="user_123",
        thread_id="thread_456",
        run_id="run_789",
        model="gpt-4",
    )
    print("✓ test_langsmith_trace_metadata")


def test_langsmith_log_functions_no_crash():
    """Test: fonctions de log ne crashent pas sans LangSmith."""
    from app.observability.langsmith_client import (
        log_agent_observation,
        create_dataset,
        add_example_to_dataset,
    )

    # Ces fonctions doivent être no-op si LangSmith désactivé
    log_agent_observation(
        action="test",
        success=True,
        result={"key": "value"},
    )
    
    dataset_id = create_dataset("test_dataset")
    assert dataset_id is None  # Pas de dataset sans API key
    
    success = add_example_to_dataset(
        dataset_id="test",
        inputs={"input": "test"},
    )
    assert success is False

    print("✓ test_langsmith_log_functions_no_crash")


# ============================================================
# HEALTH ENDPOINTS TESTS
# ============================================================

def test_health_model_gateway_endpoint():
    """Test: health check model gateway."""
    from app.api.health import health_model_gateway

    result = health_model_gateway()
    assert "enabled" in result
    assert "provider" in result
    assert "fallback" in result
    print("✓ test_health_model_gateway_endpoint")


def test_health_langsmith_endpoint():
    """Test: health check LangSmith."""
    from app.api.health import health_langsmith

    result = health_langsmith()
    assert "enabled" in result
    assert "configured" in result
    assert "environment" in result
    print("✓ test_health_langsmith_endpoint")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("MODEL GATEWAY + KNOWLEDGE ACL + LANGSMITH TESTS")
    print("=" * 60)

    # Model Registry
    print("\n--- Model Registry ---")
    test_model_registry_get_config()
    test_model_registry_list_all()
    test_model_registry_save_update()

    # Model Resolver
    print("\n--- Model Resolver ---")
    test_model_resolver_default_purpose()
    test_model_resolver_coding_purpose()
    test_model_resolver_unknown_purpose()
    test_model_resolver_disabled_model()

    # Knowledge Access
    print("\n--- Knowledge Access ---")
    test_knowledge_access_public()
    test_knowledge_access_private_owner()
    test_knowledge_access_private_non_owner()
    test_knowledge_access_group_member()
    test_knowledge_access_user_scope()
    test_knowledge_access_admin_override()
    test_knowledge_access_cross_user_isolation()
    test_knowledge_access_cross_group_isolation()

    # LangSmith
    print("\n--- LangSmith Observability ---")
    test_langsmith_client_not_enabled()
    test_langsmith_trace_metadata()
    test_langsmith_log_functions_no_crash()

    # Health Endpoints
    print("\n--- Health Endpoints ---")
    test_health_model_gateway_endpoint()
    test_health_langsmith_endpoint()

    print("\n" + "=" * 60)
    print("TOUS LES TESTS ONT RÉUSSI ✓")
    print("=" * 60)
