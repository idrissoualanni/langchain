"""Reproduction des 500 de production du 2026-11-11 (vus côté navigateur
comme des « erreurs CORS »).

1. GET /api/users/{id}/profile : ProfileOut levait une ValidationError
   (user_id et exists absents du dict renvoyé par read_profile_for_api).
2. POST /api/chat/stream : get_thread tombait sur une connexion tuée par
   Neon (IdleInTransactionSessionTimeout) — chaque SELECT laissait la
   connexion thread-local « idle in transaction ».
3. Un 500 (ou un 429) partait SANS en-têtes CORS : le navigateur masquait
   la vraie erreur derrière « No 'Access-Control-Allow-Origin' ».
"""

from __future__ import annotations

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from app.infrastructure.database.connections import AppConn, _is_read_only
from app.schemas.user import ProfileOut


# ---------------------------------------------------------------------------
# 1. Contrat du profil
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stored", "exists"),
    [(None, False), ({"name": "Awa", "description": "Terminale S"}, True)],
)
def test_profile_for_api_respecte_profileout(monkeypatch, stored, exists):
    from app.services.memory import memory
    from app.services.memory.cognitive_store import cognitive_store

    monkeypatch.setattr(cognitive_store, "latest_profile", lambda _uid: stored)
    data = memory.read_profile_for_api("u-1")

    # Avant le correctif : ValidationError (user_id, exists manquants).
    out = ProfileOut(**data, account_name=None, role=None)
    assert out.user_id == "u-1"
    assert out.exists is exists


# ---------------------------------------------------------------------------
# 2. Connexions : plus de transaction de lecture laissée ouverte
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://")
    yield eng
    eng.dispose()


def test_lecture_ne_laisse_pas_de_transaction_ouverte(engine):
    conn = AppConn(engine.connect())
    assert conn.execute("SELECT 1 AS x").fetchone()["x"] == 1
    # Avant le correctif : True → session « idle in transaction » que
    # Neon finit par tuer.
    assert conn._sa.in_transaction() is False


def test_ecriture_en_attente_reste_dans_sa_transaction(engine):
    conn = AppConn(engine.connect())
    conn.execute("CREATE TABLE t (v INTEGER)")
    conn.execute("INSERT INTO t (v) VALUES (:v)", {"v": 1})
    conn.execute("SELECT v FROM t")
    # Une lecture ne doit PAS committer une écriture non validée.
    assert conn._sa.in_transaction() is True
    conn.rollback()
    assert conn._dirty is False


class _DeadThenAlive:
    """Connexion « tuée par Neon » : première requête en échec."""

    def __init__(self, engine):
        self.engine = engine
        self.closed = False

    def execute(self, *_a, **_k):
        raise OperationalError(
            "SELECT 1",
            {},
            Exception(
                "terminating connection due to idle-in-transaction timeout"
            ),
        )

    def rollback(self):
        raise OperationalError("ROLLBACK", {}, Exception("connection already closed"))

    def close(self):
        self.closed = True


def test_lecture_rejouee_sur_connexion_neuve_si_session_tuee(engine):
    conn = AppConn(_DeadThenAlive(engine))
    # Avant le correctif : l'erreur remontait → 500.
    assert conn.execute("SELECT 2 AS x").fetchone()["x"] == 2


def test_ecriture_jamais_rejouee_si_session_tuee(engine):
    conn = AppConn(_DeadThenAlive(engine))
    conn._dirty = True  # écriture en attente : perdue avec la session
    with pytest.raises(OperationalError):
        conn.execute("SELECT 1")


@pytest.mark.parametrize(
    ("sql", "read"),
    [
        ("SELECT 1", True),
        ("  select * from t", True),
        ("SELECT * FROM t FOR UPDATE", False),
        ("WITH x AS (INSERT INTO t VALUES (1) RETURNING *) SELECT * FROM x", False),
        ("INSERT INTO t VALUES (1)", False),
    ],
)
def test_detection_lecture_seule(sql, read):
    assert _is_read_only(sql) is read


# ---------------------------------------------------------------------------
# 3. Les erreurs passent par le CORS
# ---------------------------------------------------------------------------


def _middleware_names(app):
    # user_middleware[0] = le plus externe.
    return [
        getattr(m.kwargs.get("dispatch"), "__name__", None) or m.cls.__name__
        for m in app.user_middleware
    ]


def test_500_et_429_sont_produits_sous_le_cors():
    from app.main import app

    names = _middleware_names(app)
    cors = names.index(CORSMiddleware.__name__)
    assert names.index("catch_unhandled_inside_cors") > cors
    assert names.index("_global_rate_limit_middleware") > cors


def test_exception_non_geree_devient_500_json():
    from app.main import app

    path = "/__test_boom_500"
    if not any(getattr(r, "path", None) == path for r in app.router.routes):

        @app.get(path)
        def _boom():  # pragma: no cover - exécutée via le client
            raise RuntimeError("panne simulée")

    r = TestClient(app, raise_server_exceptions=False).get(path)
    assert r.status_code == 500
    assert r.json()["code"] == "unhandled_error"
