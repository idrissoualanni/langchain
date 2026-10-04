# Test de régression — refus GÉNÉRIQUE de POST /api/auth/session.
#
# POURQUOI CE TEST EXISTE
#
# Avant, le corps de la requête était déclaré en paramètre de route
# (`payload: SessionExchange`) : FastAPI le validait et renvoyait `422`
# avec le détail Pydantic (`loc`, `msg`, `input`, `ctx`) sur TOUT corps
# malformé. AGENTS.md §2 exige `401` + message générique — un `422`
# bavard est un oracle sur ce que l'endpoint a tenté de lire.
#
# Ce test verrouille l'invariant : TOUT ce que le validateur refuse
# devient le MÊME 401 que celui d'une signature invalide. On compare
# donc les corps de réponse entre eux, pas seulement les codes : deux
# refus indistinguables par le client, c'est exactement ce qu'on veut.
import pytest
from fastapi.testclient import TestClient

from app.main import app

#: Le refus doit être BYTE-identique quelle que soit la cause.
_GENERIC_BODY = {"detail": "Token invalide ou expiré"}

#: (libellé, corps) — JSON invalide, champ absent, token vide,
#: token du mauvais type, corps vide.
MALFORMED = [
    ("json_invalide", b"{token:forge}"),
    ("champ_absent", b"{}"),
    ("token_vide", b'{"token": ""}'),
    ("token_non_string", b'{"token": 123}'),
    ("corps_vide", b""),
]


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _post(client: TestClient, body: bytes):
    return client.post(
        "/api/auth/session",
        content=body,
        headers={"Content-Type": "application/json"},
    )


@pytest.mark.parametrize("label,body", MALFORMED, ids=[m[0] for m in MALFORMED])
def test_malformed_body_is_401_generic(client: TestClient, label: str, body: bytes):
    """Tout corps refusé par le validateur → 401 + message unique."""
    r = _post(client, body)
    assert r.status_code == 401, f"{label}: attendu 401, reçu {r.status_code}"
    assert r.json() == _GENERIC_BODY, (
        f"{label}: le refus doit être générique, reçu {r.text!r}"
    )


def test_malformed_is_indistinguishable_from_bad_signature(client: TestClient):
    """Le point dur : un corps malformé NE DOIT PAS se distinguer
    d'une signature invalide (même statut, même corps).

    C'est ce qui ferme l'oracle : si les deux réponses différaient, un
    attaquant pourrait sonder la forme attendue du token.
    """
    forged = client.post(
        "/api/auth/session",
        content=b'{"token":"eyJhbGciOiJFZERTQSJ9.eyJzdWIiOiJmb3JnZWQifQ.forge"}',
        headers={"Content-Type": "application/json"},
    )
    broken = _post(client, b"{token:forge}")

    assert forged.status_code == broken.status_code == 401
    assert forged.json() == broken.json() == _GENERIC_BODY


def test_malformed_leaks_no_validation_detail(client: TestClient):
    """Aucune clé de détail de validateur ne doit subsister."""
    r = _post(client, b"{}")
    payload = r.json()
    assert set(payload) == {"detail"}, f"clés inattendues : {set(payload)}"
    for forbidden in ("loc", "msg", "input", "ctx", "errors"):
        assert forbidden not in r.text, f"'{forbidden}' fuite dans {r.text!r}"


def test_valid_token_path_still_rejects_forgery(client: TestClient):
    """Garde-fou : le chemin nominal reste fermé (pas de régression
    ouverte par le correctif). Un token bien formé mais non signé
    continue d'être refusé en 401 générique."""
    r = client.post(
        "/api/auth/session",
        content=b'{"token":"eyJhbGciOiJFZERTQSJ9.eyJzdWIiOiJmb3JnZWQifQ.forge"}',
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 401
    assert r.json() == _GENERIC_BODY


def test_session_openapi_still_documents_body(client: TestClient):
    """Le corps est lu à la main : on vérifie que le schéma OpenAPI
    n'a PAS perdu la documentation du body (sinon `/docs` ment)."""
    schema = client.get("/openapi.json").json()
    body = schema["paths"]["/api/auth/session"]["post"]["requestBody"]
    assert body["required"] is True
    props = body["content"]["application/json"]["schema"]["properties"]
    assert "token" in props


def test_get_session_unaffected(client: TestClient):
    """`GET /api/auth/session` reste un aperçu « es-tu connecté ? »
    : 200 + `authenticated: false`, jamais une erreur."""
    r = client.get("/api/auth/session")
    assert r.status_code == 200
    # `expires_in` fait partie du schema `SessionStatus` : FastAPI le
    # serialise TOUJOURS, meme a None. L'asserter ici rendrait le test
    # dependant d'un detail de serialisation qui n'a rien a voir avec le
    # refus generique verifie ci-dessus. On verifie donc l'invariant
    # utile : pas connecte, et aucune erreur.
    body = r.json()
    assert body["authenticated"] is False
    assert body.get("expires_in") is None