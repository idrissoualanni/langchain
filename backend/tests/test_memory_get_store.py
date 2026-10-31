"""Reproduction : `memory.get_store()` doit renvoyer le store LangGraph.

Bug : get_store() renvoyait le CognitiveStore (mémoire vectorielle), qui
n'a ni get/put ni list_namespaces. Chaque tool learning échouait avec
"'CognitiveStore' object has no attribute 'get'".
"""
from app.infrastructure.database import persistence
from app.services.memory import memory
from app.services.memory.cognitive_store import CognitiveStore


def test_get_store_delegue_au_store_persistant(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(persistence, "get_persistent_store", lambda: sentinel)

    assert memory.get_store() is sentinel


def test_get_store_n_est_pas_le_cognitive_store(monkeypatch):
    class FakeStore:
        def get(self, *a, **k): ...
        def put(self, *a, **k): ...
        def list_namespaces(self, *a, **k): ...

    monkeypatch.setattr(persistence, "get_persistent_store", FakeStore)

    store = memory.get_store()
    assert not isinstance(store, CognitiveStore)
    for method in ("get", "put", "list_namespaces"):
        assert callable(getattr(store, method))
