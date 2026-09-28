# Tests — validation JWT Neon Auth + tolérance d'horloge.
#
# Exécution : pytest tests/test_auth_jwt_leeway.py (depuis backend/)
#
# Contexte : une dérive d'horloge locale (iat perçu comme futur) faisait
# rejeter les tokens fraîchement émis avec ImmatureSignatureError → 401.
# Correctif : JWT_LEEWAY (défaut 60 s) passé à jwt.decode().
#
# ⚠️ Ce fichier couvre le chemin de PRODUCTION ( AUTH_MODE=neon, EdDSA ).
# Il remplace test_clerk_jwt_leeway.py ( RS256 / Clerk ) : la logique de
# leeway est load-bearing pour Neon, elle ne doit pas rester sans
# couverture après le retrait du fournisseur Clerk.
#
# Note pytest vs script : les anciens tests unitaires de ce dossier
# étaient des scripts autonomes ( sys.exit en fin de module ) qui
# font planter la collecte pytest ( INTERNALERROR ). Celui-ci est un
# vrai fichier pytest pour ne pas ajouter à ce problème.
import sys
import time

sys.path.insert(0, ".")

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519
from fastapi import HTTPException

from app.auth import resolver
from app.config import AUTH_MODE, JWT_LEEWAY

# Neon Auth signe en EdDSA / Ed25519 ( clé OKP ), PAS en RS256.
_PRIVATE = ed25519.Ed25519PrivateKey.generate()
_PUBLIC = _PRIVATE.public_key()
_OTHER_PRIVATE = ed25519.Ed25519PrivateKey.generate()

# Audience attendue : base URL connue pour que la vérif aud soit active
# ( sinon verify_neon_token la désactive explicitement ).
_AUD = "https://example.neon.tech"


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKClient:
    """Faux client JWKS — aucun accès réseau."""

    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(_PUBLIC)


def make_token(
    iat_offset=0,
    exp_offset=3600,
    aud=_AUD,
    private_key=None,
):
    """Construit un JWT de test ; iat_offset permet de simuler la dérive."""
    now = int(time.time())
    payload = {
        "sub": "user_test_leeway",
        "iat": now + iat_offset,
        "exp": now + exp_offset,
    }
    if aud is not None:
        payload["aud"] = aud
    return jwt.encode(
        payload,
        private_key if private_key is not None else _PRIVATE,
        algorithm="EdDSA",
    )


def verify(token):
    """Retourne (ok, exception_name) sans lever."""
    try:
        resolver.verify_neon_token(token)
        return True, None
    except Exception as exc:  # noqa: BLE001 - on teste le type
        return False, type(exc).__name__


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Faux JWKS + audience fixe, restaurés après chaque test."""
    monkeypatch.setattr(resolver, "_neon_jwk_client", _FakeJWKClient())
    monkeypatch.setattr(resolver, "NEON_AUTH_BASE_URL", _AUD)


# ------------------------------------------------------------------
# Configuration — garde-fous
# ------------------------------------------------------------------
def test_jwt_leeway_default_is_60():
    assert JWT_LEEWAY == 60


def test_auth_mode_default_is_neon():
    """Un AUTH_MODE absent NE DOIT PAS retomber sur un fournisseur mort.

    Régression : le défaut était "clerk" (config.py). Une variable
    d'environnement mal orthographiée faisait bascule la prod sur une
    vérification de signature via un JWKS inexistant.
    """
    assert AUTH_MODE == "neon"


# ------------------------------------------------------------------
# Validation du token
# ------------------------------------------------------------------
def test_valid_token_accepted():
    ok, err = verify(make_token(iat_offset=-5))
    assert ok, err


def test_clock_drift_within_leeway_accepted():
    """Dérive locale absorbée — c'est le bug corrigé à l'origine."""
    skew = max(1, JWT_LEEWAY - 5)
    ok, err = verify(make_token(iat_offset=skew))
    assert ok, err


def test_clock_drift_beyond_leeway_rejected():
    beyond = JWT_LEEWAY + 30
    ok, err = verify(make_token(iat_offset=beyond))
    assert not ok
    assert err == "ImmatureSignatureError"


def test_expired_beyond_leeway_rejected():
    expired_by = JWT_LEEWAY + 30
    ok, err = verify(make_token(iat_offset=-10, exp_offset=-expired_by))
    assert not ok
    assert err == "ExpiredSignatureError"


def test_expiry_within_leeway_tolerated():
    """Le leeway couvre AUSSI `exp`, pas seulement `iat`.

    Comportement voulu et documenté : la dérive d'horloge joue dans
    les deux sens. Ce test épingle ce choix pour qu'un futur
    resserrement du leeway soit une décision explicite.
    """
    ok, err = verify(make_token(iat_offset=-10, exp_offset=-5))
    assert ok, err


def test_invalid_signature_rejected():
    """Token signé par une AUTRE clé Ed25519 → rejet."""
    ok, err = verify(make_token(private_key=_OTHER_PRIVATE))
    assert not ok
    assert err == "InvalidSignatureError"


def test_wrong_audience_rejected():
    ok, err = verify(make_token(aud="https://pas-le-bon.neon.tech"))
    assert not ok
    assert err == "InvalidAudienceError"


def test_leeway_is_actually_applied(monkeypatch):
    """Preuve que le leeway agit : à 0, le même token est refusé."""
    skew = max(1, JWT_LEEWAY - 5)
    monkeypatch.setattr(resolver, "JWT_LEEWAY", 0)
    ok, err = verify(make_token(iat_offset=skew))
    assert not ok
    assert err == "ImmatureSignatureError"


# ------------------------------------------------------------------
# Fail-closed sur AUTH_MODE
# ------------------------------------------------------------------
def test_unknown_auth_mode_raises_503(monkeypatch):
    """Régression critique : _resolve_from_token ne doit JAMAIS
    retourner None.

    Elle tombait hors de tout `if` et retournait None. Une dépendance
    FastAPI recevant None casse l'isolation SILENCIEUSEMENT — ni 401,
    ni log, ni trace.
    """
    monkeypatch.setattr(resolver, "AUTH_MODE", "clerk")
    with pytest.raises(HTTPException) as exc:
        resolver._resolve_from_token("dev:quelconque")
    assert exc.value.status_code == 503
