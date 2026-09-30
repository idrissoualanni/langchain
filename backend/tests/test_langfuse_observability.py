"""
LANGFUSE OBSERVABILITY TESTS

Tests de la couche d'observabilité Langfuse (module unique
``app/observability/langfuse.py``).

Ce que l'on vérifie :
- activation : is_enabled() ne dépend QUE de la config applicative
  (LANGFUSE_ENABLED + clés + base_url) ;
- résilience : sans package / sans clés / serveur injoignable, tous les
  appels retournent des no-op (liste vide, config inchangée, client None)
  et AUCUNE fonction ne lève ;
- confidentialité : mask_payload masque les valeurs sensibles.
- non-régression : l'app démarre et répond même si Langfuse est inutilisable.
"""

import pytest
from unittest.mock import patch

from app.observability.langfuse import (
    mask_payload,
    is_enabled,
    get_client,
    get_callbacks,
    trace_metadata,
    invoke_config,
    shutdown_langfuse,
)


# ---------------------------------------------------------------------------
# Fixtures utilitaires
# ---------------------------------------------------------------------------


def _enable_langfuse(monkeypatch, *, keys=True, base_url=True):
    """Active Langfuse dans l'environnement (par défaut : config complète)."""
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    if keys:
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test-public-key")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test-secret-key")
    else:
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    if base_url:
        monkeypatch.setenv("LANGFUSE_BASE_URL", "http://localhost:3000")
    else:
        monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)


@pytest.fixture(autouse=True)
def _reset_client_singleton():
    """Le client Langfuse est un singleton lazy : on le remet à None à
    chaque test pour ne pas contaminer les autres tests."""
    import app.observability.langfuse as mod

    mod._client = None
    yield
    mod._client = None


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------


class TestLangfuseActivation:
    def test_disabled_by_default(self, monkeypatch):
        """Sans LANGFUSE_ENABLED=true, Langfuse est désactivé."""
        monkeypatch.delenv("LANGFUSE_ENABLED", raising=False)
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)
        assert is_enabled() is False

    def test_enabled_requires_all_keys(self, monkeypatch):
        """Activé MAIS sans clés ni URL → désactivé (pas de visée
        cloud.langfuse.com par accident)."""
        _enable_langfuse(monkeypatch, keys=False)
        assert is_enabled() is False

        _enable_langfuse(monkeypatch, keys=True, base_url=False)
        assert is_enabled() is False

    def test_enabled_with_complete_config(self, monkeypatch):
        _enable_langfuse(monkeypatch)
        assert is_enabled() is True

    def test_enabled_respects_explicit_false(self, monkeypatch):
        """LANGFUSE_ENABLED=false prime sur clés présentes."""
        _enable_langfuse(monkeypatch)
        monkeypatch.setenv("LANGFUSE_ENABLED", "false")
        assert is_enabled() is False

    def test_host_alias_accepted(self, monkeypatch):
        """LANGFUSE_HOST est l'ancien alias du SDK : on l'accepte quand
        LANGFUSE_BASE_URL est absent."""
        _enable_langfuse(monkeypatch, base_url=False)
        monkeypatch.setenv("LANGFUSE_HOST", "http://localhost:3000")
        assert is_enabled() is True


# ---------------------------------------------------------------------------
# Callbacks / résilience
# ---------------------------------------------------------------------------


class TestLangfuseResilience:
    def test_callbacks_vides_quand_desactive(self, monkeypatch):
        """Désactivé → liste de callbacks VIDE (contrat principal)."""
        monkeypatch.setenv("LANGFUSE_ENABLED", "false")
        assert get_callbacks() == []

    def test_callbacks_vides_sans_cle(self, monkeypatch):
        _enable_langfuse(monkeypatch, keys=False)
        assert get_callbacks() == []

    def test_callbacks_noop_si_package_absent(self, monkeypatch):
        """Si le package langfuse ne peut pas être importé, l'app continue
        (callbacks vides, client None, aucune exception)."""
        _enable_langfuse(monkeypatch)
        import sys

        monkeypatch.setitem(sys.modules, "langfuse", None)
        assert get_callbacks() == []
        assert get_client() is None

    def test_invoke_config_inchange_quand_desactive(self, monkeypatch):
        """Config d'invoke INCHANGÉE (même objet) si Langfuse inutilisable."""
        monkeypatch.setenv("LANGFUSE_ENABLED", "false")
        base = {"configurable": {"thread_id": "t1", "user_id": "u1"}}
        result = invoke_config(base, user_id="u1", session_id="t1")
        assert result is base  # même objet, zéro mutation

    def test_invoke_config_ignore_package_absent(self, monkeypatch):
        """Avec package absent (mais config valide) : config inchangée."""
        _enable_langfuse(monkeypatch)
        import sys

        monkeypatch.setitem(sys.modules, "langfuse", None)
        base = {"configurable": {"thread_id": "t1"}}
        assert invoke_config(base, "u1", "t1") is base

    def test_shutdown_langfuse_ne_leve_jamais(self, monkeypatch):
        """shutdown sans client (désactivé) ne lève pas."""
        monkeypatch.setenv("LANGFUSE_ENABLED", "false")
        shutdown_langfuse()  # ne doit pas lever

    def test_shutdown_langfuse_sans_package(self, monkeypatch):
        """shutdown avec config valide mais package absent : ne lève pas."""
        _enable_langfuse(monkeypatch)
        import sys

        monkeypatch.setitem(sys.modules, "langfuse", None)
        shutdown_langfuse()

    def test_get_client_none_sans_config(self, monkeypatch):
        monkeypatch.setenv("LANGFUSE_ENABLED", "false")
        assert get_client() is None


# ---------------------------------------------------------------------------
# Métadonnées / confidentialité
# ---------------------------------------------------------------------------


class TestLangfuseMetadata:
    def test_trace_metadata_vide_si_desactive(self, monkeypatch):
        monkeypatch.setenv("LANGFUSE_ENABLED", "false")
        assert trace_metadata(user_id="u1", session_id="t1") == {}

    def test_trace_metadata_ids_internes(self, monkeypatch):
        _enable_langfuse(monkeypatch)
        meta = trace_metadata(user_id="uuid-intern", session_id="thread-42")
        assert meta["langfuse_user_id"] == "uuid-intern"
        assert meta["langfuse_session_id"] == "thread-42"

    def test_trace_metadata_omits_empty(self, monkeypatch):
        _enable_langfuse(monkeypatch)
        assert trace_metadata(user_id="", session_id="") == {}


# ---------------------------------------------------------------------------
# Masquage des valeurs sensibles
# ---------------------------------------------------------------------------


class TestLangfuseMasking:
    def test_masks_password(self):
        assert mask_payload({"password": "s3cret"}) == {"password": "***"}

    def test_masks_authorization_value(self):
        payload = {"headers": {"authorization": "Bearer jwt-token"}}
        masked = mask_payload(payload)
        assert masked["headers"]["authorization"] == "***"

    def test_redacts_x_api_key_header(self):
        """X-Api-Key (entête) est SUPPRIMÉ, pas seulement masqué."""
        masked = mask_payload({"headers": {"x-api-key": "clef"}})
        assert "x-api-key" not in masked["headers"]

    def test_masks_nested_structures(self):
        payload = {"data": {"api_key": "abc", "ok": "valeur normale"}}
        masked = mask_payload(payload)
        assert masked["data"]["api_key"] == "***"
        assert masked["data"]["ok"] == "valeur normale"

    def test_masks_list_items(self):
        payload = [{"jwt": "t", "token": "x"}, "texte libre"]
        assert mask_payload(payload)[0] == {"jwt": "***", "token": "***"}
        assert mask_payload(payload)[1] == "texte libre"

    def test_leaves_plain_strings(self):
        """Chaîne isolée : on ne peut pas juger, on la laisse."""
        assert mask_payload("mot de passe en clair") == "mot de passe en clair"

    def test_masks_authorization_field(self):
        assert mask_payload({"Authorization": "Bearer eyJ"}) == {
            "Authorization": "***"
        }


# ---------------------------------------------------------------------------
# Non-régression : l'app répond sans Langfuse
# ---------------------------------------------------------------------------


class TestLangfuseNonRegression:
    def test_health_ok_sans_langfuse(self):
        """L'app démarre et /api/health répond même si Langfuse est absent
        (module no-op : aucune exception à l'import, aucun crash au boot)."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] in ["ok", "degraded"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])