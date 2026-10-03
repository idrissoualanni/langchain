# Tests — tolérance de l'audience JWT Neon Auth.
#
# Exécution : pytest tests/test_neon_jwt_audience.py (depuis backend/)
#
# POURQUOI CE FICHIER EXISTE
# -------------------------
# Un 401 « token invalide ou expiré » frappait la production alors que le
# jeton était parfaitement valide. La cause : `verify_neon_token` ne
# comparait l'audience qu'à UNE forme d'URL — celle de
# NEON_AUTH_BASE_URL. Or l'`aud` que pose Better Auth se lit selon la
# version et le déploiement avec ou sans slash final, et pointe tantôt la
# base du service, tantôt son origine seule. Toutes les autres écritures
# d'un secret que nous possédons nous-même étaient rejetées.
#
# Aggravant : le message renvoyé était IDENTIQUE à celui d'une mauvaise
# signature. Deux pannes auxCauses opposées, une seule chaîne d'erreur,
# donc aucune piste. Ici on épingle les deux à part.
#
# Ce que ces tests garantissent :
#   - toutes les écritures légitimes de NOTRE audience sont acceptées ;
#   - une audience ÉTRANGÈRE reste refusée ( la tolérance n'ouvre rien ) ;
#   - un refus d'audience est journalisé et distinct d'un refus de
#     signature.
#
# ⚠️ Aucun accès réseau : faux client JWKS, clé Ed25519 générée à la volée.
# Vrai fichier pytest ( pas un script autonome ) : les vieux scripts de ce
# dossier font planter la collecte globale avec INTERNALERROR.
import sys
import time

sys.path.insert(0, ".")

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from app.auth import resolver

# Neon Auth signe en EdDSA / Ed25519 ( clé OKP ), PAS en RS256.
_PRIVATE = ed25519.Ed25519PrivateKey.generate()
_PUBLIC = _PRIVATE.public_key()

# Les deux variables telles qu'on les trouve en prod. Le backend local
# (.env) et Render ne portent PAS forcément les mêmes valeurs — c'est
# exactement le fait qui rendait le 401 non reproductible.
_BASE = "https://ep-example.neonauth.c-6.eu-central-1.aws.neon.tech/neondb/auth"
_ORIGIN = "https://ep-example.neonauth.c-6.eu-central-1.aws.neon.tech"
_JWKS = _BASE + "/.well-known/jwks.json"


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKClient:
    """Faux client JWKS — aucun accès réseau."""

    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(_PUBLIC)


def make_token(aud=_BASE, **extra):
    now = int(time.time())
    payload = {"sub": "user_test_aud", "iat": now, "exp": now + 3600}
    if aud is not None:
        payload["aud"] = aud
    payload.update(extra)
    return jwt.encode(payload, _PRIVATE, algorithm="EdDSA")


def verify(token):
    """Retourne (ok, nom_exception) sans lever."""
    try:
        resolver.verify_neon_token(token)
        return True, None
    except Exception as exc:  # noqa: BLE001 — on teste le type
        return False, type(exc).__name__


@pytest.fixture
def cfg(monkeypatch):
    """Config Neon « nominale » : base + JWKS cohérentes entre elles."""
    monkeypatch.setattr(resolver, "_neon_jwk_client", _FakeJWKClient())
    monkeypatch.setattr(resolver, "NEON_AUTH_BASE_URL", _BASE)
    monkeypatch.setattr(resolver, "NEON_AUTH_JWKS_URL", _JWKS)
    return monkeypatch


# ------------------------------------------------------------------
# Construction de la liste d'audiences attendues
# ------------------------------------------------------------------
def test_audience_derive_du_jwks(cfg):
    """Le JWKS suffit à derivé l'audience : NEON_AUTH_BASE_URL est optionnel.

    C'est le filet de sécurité : sur Render, NEON_AUTH_BASE_URL n'est
    déclarée ni dans render.yaml ni au dashboard. Sans cette dérivation,
    la seule variable présente au déploiement ne servait à rien.
    """
    cfg.setattr(resolver, "NEON_AUTH_BASE_URL", "")
    # La base ET son origine seule : Better Auth écrit l'une ou l'autre.
    assert resolver._expected_audiences() == [_BASE, _ORIGIN]


def test_audience_declenchee_une_seule_fois(cfg):
    """Base et JWKS identiques → une seule entrée, pas deux doublons."""
    assert resolver._expected_audiences() == [_BASE, _ORIGIN]


def test_audience_sans_slash_final(cfg):
    """Un slash final en config ne crée pas d'entrée distincte."""
    cfg.setattr(resolver, "NEON_AUTH_BASE_URL", _BASE + "/")
    assert resolver._expected_audiences() == [_BASE, _ORIGIN]


def test_audience_vide_sans_config(cfg):
    """Aucune config → liste vide : on n'exige rien, on ne devine pas."""
    cfg.setattr(resolver, "NEON_AUTH_BASE_URL", "")
    cfg.setattr(resolver, "NEON_AUTH_JWKS_URL", "")
    assert resolver._expected_audiences() == []


# ------------------------------------------------------------------
# Les écritures légitimes passent
# ------------------------------------------------------------------
def test_audience_exacte_acceptee(cfg):
    ok, err = verify(make_token(aud=_BASE))
    assert ok, err


def test_audience_avec_slash_final_acceptee(cfg):
    """Slash final côté jeton : c'était un 401 pour un jeton valide."""
    ok, err = verify(make_token(aud=_BASE + "/"))
    assert ok, err


def test_audience_en_liste_acceptee(cfg):
    """RFC 7519 : `aud` est chaîne OU liste. Les deux sont valides."""
    ok, err = verify(make_token(aud=["https://autre.service", _BASE]))
    assert ok, err


def test_audience_origine_seule_acceptee(cfg):
    """`aud` = origine seule ( sans /neondb/auth ) : c'est une écriture réelle.

    Selon la version de Better Auth et la façon dont le service est
    exposé, `aud` vaut tantôt la base du service, tantôt son origine.
    Refuser la seconde forma rejetait un jeton parfaitement valide.
    """
    ok, err = verify(make_token(aud=_ORIGIN))
    assert ok, err


def test_audience_origine_seule_acceptee_meme_si_base_differente(cfg):
    """L'origine prime même quand NEON_AUTH_BASE_URL est périmée.

    Le JWKS est la seule source qui fait autorité — c'est de lui qu'on
    tire la clé de signature. Si BASE_URL traîne une valeur d'un ancien
    déploiement, l'origine du JWKS courant doit suffire.
    """
    cfg.setattr(resolver, "NEON_AUTH_BASE_URL", "https://ancien-projet/auth")
    ok, err = verify(make_token(aud=_ORIGIN))
    assert ok, err


def test_audience_derivee_du_jwks_acceptee_meme_si_base_differente(cfg):
    """Si BASE_URL est périmée mais le JWKS est bon, on accepte quand même.

    Cas réel : Render a pu garder une NEON_AUTH_BASE_URL d'un ancien
    déploiement. Le JWKS, lui, pointe toujours le projet courant — c'est
    lui qui fournit la clé de signature, donc lui qui fait autorité.
    """
    cfg.setattr(resolver, "NEON_AUTH_BASE_URL", "https://ancien-projet/auth")
    ok, err = verify(make_token(aud=_BASE))
    assert ok, err


def test_audience_non_verifiee_si_aucune_config(cfg):
    """Sans config, un jeton portant un aud quelconque passe.

    Choix explicite : on ne peut rien exiger, et refuser tout jeton
    simplement parce qu'une variable manque casserait la prod en silence.
    La signature reste vérifiée — c'est elle qui fait autorité.
    """
    cfg.setattr(resolver, "NEON_AUTH_BASE_URL", "")
    cfg.setattr(resolver, "NEON_AUTH_JWKS_URL", "")
    ok, err = verify(make_token(aud="https://nimporte-quoi.example"))
    assert ok, err


# ------------------------------------------------------------------
# La tolérance n'ouvre rien
# ------------------------------------------------------------------
def test_audience_etrangere_refusee(cfg):
    cfg.setattr(resolver, "NEON_AUTH_BASE_URL", "https://ancien-projet/auth")
    ok, err = verify(make_token(aud="https://attaquant.example"))
    assert not ok
    assert err == "InvalidAudienceError"


def test_audience_absente_refusee_si_config(cfg):
    """Config exigeante + jeton sans `aud` → refus, pas de passe-partout."""
    ok, err = verify(make_token(aud=None))
    assert not ok
    assert err == "InvalidAudienceError"


def test_prefixe_ou_suffixe_non_accepte(cfg):
    """Le rstrip('/') ne doit pas devenir une comparaison laxiste.

    `aud` = base + suffixe n'est PAS notre audience : une telle
    tolérance laisserait passer un jeton destiné à une autre ressource du
    même projet. Le refus est vérifié explicitement.
    """
    for hostile in (
        _BASE + "/../evil",
        _BASE + ".evil.example",
        "https://evil.example" + _BASE,
        _BASE + "?redirect=evil",
        _BASE + "#frag",
    ):
        ok, err = verify(make_token(aud=hostile))
        assert not ok, hostile
        assert err == "InvalidAudienceError", hostile


def test_audience_vide_ou_non_chaine_refusee(cfg):
    """Ni une chaîne vide ni un nombre ne peuvent « matcher » une liste."""
    for hostile in ("", 42, [None], {}):
        ok, err = verify(make_token(aud=hostile))
        assert not ok, repr(hostile)
        assert err == "InvalidAudienceError", repr(hostile)


# ------------------------------------------------------------------
# Le refus est enfin diagnosticable
# ------------------------------------------------------------------
def test_refus_audience_journalise_le_motif(cfg, monkeypatch):
    """Un mauvais `aud` doit laisser une trace lisible.

    C'est tout l'intérêt du correctif : avant, ce refus se confondait
    avec une mauvaise signature dans un message identique. Le log nomme
    l'audience reçue, l'audience attendue et le `kid` — de quoi trancher
    en un coup d'œil aux logs Render.
    """
    events = []
    monkeypatch.setattr(
        resolver, "log_event", lambda *a, **kw: events.append((a, kw))
    )
    ok, err = verify(make_token(aud="https://attaquant.example"))
    assert not ok and err == "InvalidAudienceError"
    assert len(events) == 1
    args, kwargs = events[0]
    assert args[0] == "AUTH_AUD_MISMATCH"
    msg = kwargs.get("message", "")
    assert "https://attaquant.example" in msg
    assert _BASE in msg  # l'attendu est nommé lui aussi


def test_claims_absents_nomme_dans_le_log(cfg, monkeypatch):
    """Le log liste les claims vus : un `sub`/`iat` manquant se remarque."""
    events = []
    monkeypatch.setattr(
        resolver, "log_event", lambda *a, **kw: events.append((a, kw))
    )
    token = jwt.encode(
        {
            "sub": "u",
            "iat": int(time.time()),
            "exp": int(time.time()) + 60,
            "aud": "https://attaquant.example",
            "role": "user",
        },
        _PRIVATE,
        algorithm="EdDSA",
    )
    verify(token)
    msg = events[0][1].get("message", "")
    assert "'aud'" in msg and "'sub'" in msg and "'role'" in msg


def test_refus_signature_ne_journalise_pas_daudience(cfg, monkeypatch):
    """Une VRAIE mauvaise signature ne doit pas FALSEMENT accuser l'aud.

    Symétrique du test précédent : le nouveau décodage non vérifié ne
    doit pas transformer chaque 401 en soupçon d'audience. Sans aud
    personnalisé, aucun log AUTH_AUD_MISMATCH.
    """
    events = []
    monkeypatch.setattr(
        resolver, "log_event", lambda *a, **kw: events.append((a, kw))
    )
    autre = ed25519.Ed25519PrivateKey.generate()
    token = jwt.encode(
        {
            "sub": "u",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "aud": _BASE,
        },
        autre,
        algorithm="EdDSA",
    )
    ok, err = verify(token)
    assert not ok and err == "InvalidSignatureError"
    assert events == []


def test_aud_borne_en_longueur():
    """Un `aud` de 10 000 caractères ne doit pas noyer la ligne de log."""
    out = resolver._safe_aud("x" * 10_000)
    assert len(out) <= 200


def test_aud_liste_bornee():
    """Liste enorme → bornée en nombre d'éléments ET en longueur."""
    out = resolver._safe_aud([f"https://a{i}.example" for i in range(50)])
    assert out.startswith("[") and out.endswith("]")
    assert len(out) <= 5 * 80 + 2 + 4  # 5 éléments + crochets + virgules