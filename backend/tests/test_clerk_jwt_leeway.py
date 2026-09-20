# Tests unitaires — validation JWT Clerk + tolérance d'horloge.
#
# Exécution : python tests/test_clerk_jwt_leeway.py (depuis backend/)
#
# Contexte : une dérive d'horloge locale (iat perçu comme futur) faisait
# rejeter les tokens fraîchement émis avec ImmatureSignatureError → 401.
# Correctif : CLERK_JWT_LEEWAY (défaut 60 s) passé à jwt.decode().
#
# Couvre :
#   token valide                                  → accepté
#   token fraîchement émis (dérive < leeway)      → accepté
#   token au-delà du leeway (iat trop futur)      → rejeté
#   token expiré                                  → rejeté
#   signature invalide                            → rejetée
#   issuer invalide                               → rejeté
#   le leeway configuré est réellement appliqué   → preuve par leeway=0
import time
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

sys.path.insert(0, ".")

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import CLERK_ISSUER, CLERK_JWT_LEEWAY
from app.auth import resolver

PASS = 0
FAIL = 0


def check(label, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"[PASS] {label}")
    else:
        FAIL += 1
        print(f"[FAIL] {label} -- {detail}")


# ------------------------------------------------------------------
# Clés et faux client JWKS (aucune dépendance réseau)
# ------------------------------------------------------------------
_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKClient:
    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(_public_key)


# Remplacer le client JWKS réseau par notre clé de test.
resolver._get_jwk_client = lambda: _FakeJWKClient()


def make_token(
    iat_offset=0,
    exp_offset=3600,
    issuer=CLERK_ISSUER,
    public_key=None,
    private_key=None,
):
    """Construit un JWT de test ; iat_offset permet de simuler la dérive."""
    now = int(time.time())
    payload = {
        "sub": "user_test_leeway",
        "iat": now + iat_offset,
        "exp": now + exp_offset,
    }
    if issuer is not None:
        payload["iss"] = issuer
    return jwt.encode(
        payload,
        private_key if private_key is not None else _private_key,
        algorithm="RS256",
    )


def verify(token):
    """Retourne (ok, exception_name) sans lever."""
    try:
        resolver.verify_clerk_token(token)
        return True, None
    except Exception as exc:  # noqa: BLE001 - on teste le type
        return False, type(exc).__name__


# ------------------------------------------------------------------
# 0. Configuration
# ------------------------------------------------------------------
check(
    "CFG1: CLERK_JWT_LEEWAY défaut = 60",
    CLERK_JWT_LEEWAY == 60,
    f"valeur={CLERK_JWT_LEEWAY}",
)


# ------------------------------------------------------------------
# 1. token valide → accepté
# ------------------------------------------------------------------
ok, err = verify(make_token(iat_offset=-5))
check("JWT1: token valide → accepté", ok, str(err))


# ------------------------------------------------------------------
# 2. dérive d'horloge < leeway (iat futur) → accepté
# ------------------------------------------------------------------
skew = max(1, CLERK_JWT_LEEWAY - 5)
ok, err = verify(make_token(iat_offset=skew))
check(
    f"JWT2: iat futur (+{skew}s < leeway) → accepté",
    ok,
    str(err),
)


# ------------------------------------------------------------------
# 3. au-delà du leeway → rejeté
# ------------------------------------------------------------------
beyond = CLERK_JWT_LEEWAY + 30
ok, err = verify(make_token(iat_offset=beyond))
check(
    f"JWT3: iat futur (+{beyond}s > leeway) → rejeté",
    (not ok) and err == "ImmatureSignatureError",
    f"ok={ok} err={err}",
)


# ------------------------------------------------------------------
# 4. token expiré → rejeté
# ------------------------------------------------------------------
ok, err = verify(make_token(iat_offset=-7200, exp_offset=-3600))
check(
    "JWT4: token expiré → rejeté",
    (not ok) and err == "ExpiredSignatureError",
    f"ok={ok} err={err}",
)


# ------------------------------------------------------------------
# 5. signature invalide → rejetée
# ------------------------------------------------------------------
# Signer avec une autre clé privée → signature invalide.
_other_private = rsa.generate_private_key(
    public_exponent=65537, key_size=2048
)
bad_sig = jwt.encode(
    {
        "sub": "user_test_leeway",
        "iat": int(time.time()) - 5,
        "exp": int(time.time()) + 3600,
        "iss": CLERK_ISSUER,
    },
    _other_private,
    algorithm="RS256",
)
ok, err = verify(bad_sig)
check(
    "JWT5: signature invalide → rejetée",
    (not ok) and err == "InvalidSignatureError",
    f"ok={ok} err={err}",
)


# ------------------------------------------------------------------
# 6. issuer invalide → rejeté
# ------------------------------------------------------------------
if CLERK_ISSUER:
    ok, err = verify(
        make_token(issuer="https://issuer-invalide.example.com")
    )
    check(
        "JWT6: issuer invalide → rejeté",
        (not ok) and err == "InvalidIssuerError",
        f"ok={ok} err={err}",
    )
else:
    print("[SKIP] JWT6: CLERK_ISSUER non configuré")


# ------------------------------------------------------------------
# 7. preuve que le leeway configuré est réellement appliqué
#    (leeway=0 → le même token dérivé est rejeté)
# ------------------------------------------------------------------
_saved = resolver.CLERK_JWT_LEEWAY
try:
    resolver.CLERK_JWT_LEEWAY = 0
    ok0, err0 = verify(make_token(iat_offset=skew))
finally:
    resolver.CLERK_JWT_LEEWAY = _saved
check(
    "JWT7: leeway=0 → même dérive rejetée (leeway bien appliqué)",
    (not ok0) and err0 == "ImmatureSignatureError",
    f"ok={ok0} err={err0}",
)


# ------------------------------------------------------------------
# RESULTAT
# ------------------------------------------------------------------
print(f"\n===== {PASS}/{PASS + FAIL} PASS =====")
if FAIL:
    sys.exit(1)
