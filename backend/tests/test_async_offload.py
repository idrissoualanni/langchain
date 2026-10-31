"""Reproduction : du code bloquant s'exécutait DANS la boucle d'événements.

`upload_object` (async) appelait put_object (S3 + base) et l'indexation
RAG (extraction + embeddings) en direct : pendant un upload, plus aucune
requête — flux SSE compris — n'était servie par le worker.
"""
from __future__ import annotations

import asyncio
import inspect

import pytest
from fastapi.testclient import TestClient

from app.auth.resolver import CurrentUser, get_current_user

USER = "11111111-1111-1111-1111-111111111111"


def _in_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def test_upload_execute_le_stockage_hors_de_la_boucle(monkeypatch):
    import app.api.storage as storage_api
    from app.main import app

    seen: dict[str, bool] = {}

    def fake_put_object(**kwargs):
        seen["put_object"] = _in_event_loop()
        return {"object_id": "o1", "storage": "s3", "deduped": False}

    def fake_index(*args):
        seen["index"] = _in_event_loop()
        return True

    import app.infrastructure.database.connections as connections

    monkeypatch.setattr(connections, "init_db", lambda: None)
    monkeypatch.setattr(storage_api, "put_object", fake_put_object)
    monkeypatch.setattr(storage_api, "_index_document", fake_index)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        external_user_id="ext", user_id=USER, name="T", role="user"
    )
    try:
        r = TestClient(app).post(
            f"/api/users/{USER}/storage/document",
            files={"file": ("notes.txt", b"Une boucle for parcourt une liste.", "text/plain")},
        )
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 200, r.text
    assert seen == {"put_object": False, "index": False}


@pytest.mark.parametrize(
    "module, names",
    [
        ("app.api.admin.dashboard", ["get_dashboard_metrics", "get_activity_stats"]),
        ("app.api.admin.observability", ["get_observability_summary", "get_recent_runs", "get_error_log"]),
        ("app.api.admin.providers", ["get_providers", "update_provider"]),
        ("app.api.user.memory", ["get_learning_map", "update_mastery"]),
    ],
)
def test_routes_sans_await_ne_sont_plus_async(module, names):
    """Sans `await`, une route async bloque la boucle ; en `def`, FastAPI
    l'exécute dans son pool de threads."""
    import importlib

    mod = importlib.import_module(module)
    for name in names:
        fn = inspect.unwrap(getattr(mod, name))
        assert not inspect.iscoroutinefunction(fn), f"{module}.{name}"
