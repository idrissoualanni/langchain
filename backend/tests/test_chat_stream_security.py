"""Reproduction — Lot 1 sécurité : flux de chat, souveraineté, téléchargement.

1. `GET /api/chat/stream` lançait un run : hors du contrôle d'Origine
   (réservé aux méthodes mutantes) alors que le cookie est SameSite=None,
   et le message finissait dans l'URL donc dans les journaux d'accès.
2. Un admin pouvait converser dans le thread d'un autre utilisateur et
   lire sa mémoire (AGENTS.md, Souveraineté).
3. Un nom de fichier non latin-1 faisait échouer le téléchargement.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth.resolver import CurrentUser, get_current_user
from app.config import ALLOWED_ORIGINS

OWNER = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"
THREAD = "33333333-3333-3333-3333-333333333333"


def _user(user_id: str, role: str = "user") -> CurrentUser:
    return CurrentUser(
        external_user_id=f"ext-{user_id[:4]}", user_id=user_id, name="T", role=role
    )


@pytest.fixture
def client(monkeypatch):
    import app.api.chat as chat_api
    import app.api.memory as memory_api
    import app.api.users as users_api
    from app.main import app

    noop = lambda: None  # noqa: E731
    for mod in (chat_api, memory_api, users_api):
        monkeypatch.setattr(mod, "init_db", noop)

    owned = {THREAD: OWNER}
    thread_of = lambda tid: {"thread_id": tid, "user_id": owned[tid]} if tid in owned else None  # noqa: E731
    belongs = lambda tid, uid: owned.get(tid) == uid  # noqa: E731
    for mod in (chat_api, memory_api):
        monkeypatch.setattr(mod, "get_thread", thread_of)
        monkeypatch.setattr(mod, "thread_belongs_to_user", belongs)
    monkeypatch.setattr(users_api, "get_user", lambda uid: {"user_id": uid})

    async def fake_stream(**kwargs):
        yield {"event": "RUN_END", "message": "ok"}

    monkeypatch.setattr(chat_api, "run_agent_stream", fake_stream)

    def as_user(user: CurrentUser) -> TestClient:
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app)

    yield as_user
    app.dependency_overrides.clear()


def _body(user_id: str = OWNER, thread_id: str = THREAD) -> dict:
    return {"user_id": user_id, "thread_id": thread_id, "message": "Bonjour"}


def test_stream_en_get_n_existe_plus(client):
    c = client(_user(OWNER))
    r = c.get(
        "/api/chat/stream",
        params={"user_id": OWNER, "thread_id": THREAD, "message": "Bonjour"},
    )
    assert r.status_code == 405


def test_stream_post_depuis_une_origine_tierce_est_refuse(client):
    c = client(_user(OWNER))
    r = c.post(
        "/api/chat/stream",
        json=_body(),
        headers={"Origin": "https://evil.example"},
    )
    assert r.status_code == 403


def test_stream_post_legitime_renvoie_le_flux(client):
    c = client(_user(OWNER))
    r = c.post(
        "/api/chat/stream",
        json=_body(),
        headers={"Origin": ALLOWED_ORIGINS[0]},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert "RUN_END" in r.text


def test_stream_user_id_d_autrui_est_refuse(client):
    c = client(_user(OTHER))
    r = c.post("/api/chat/stream", json=_body(user_id=OWNER))
    assert r.status_code == 403


@pytest.mark.parametrize("route", ["/api/chat", "/api/chat/stream"])
def test_admin_ne_peut_pas_converser_dans_le_thread_d_autrui(client, route):
    c = client(_user(OTHER, role="admin"))
    r = c.post(route, json=_body(user_id=OWNER))
    assert r.status_code == 403


def test_admin_ne_lit_pas_l_etat_du_thread_d_autrui(client):
    c = client(_user(OTHER, role="admin"))
    r = c.get(f"/api/threads/{THREAD}/state")
    assert r.status_code == 403


@pytest.mark.parametrize(
    "path",
    [
        f"/api/users/{OWNER}/memory",
        f"/api/users/{OWNER}/memory/facts",
        f"/api/users/{OWNER}/memory/search?q=python",
    ],
)
def test_admin_ne_lit_pas_la_memoire_d_autrui(client, path):
    c = client(_user(OTHER, role="admin"))
    assert c.get(path).status_code == 403


def test_content_disposition_accepte_tout_nom_de_fichier():
    from urllib.parse import unquote

    from app.api.storage import _content_disposition

    name = 'cours’été "final" 📘.pdf'
    header = _content_disposition(name)

    header.encode("latin-1")  # ne lève plus : en-tête HTTP valide
    assert 'filename="' in header
    assert unquote(header.split("filename*=UTF-8''", 1)[1]) == name
