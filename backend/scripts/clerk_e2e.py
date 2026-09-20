# Mission VALIDATION CLERK E2E — harness isolé.
#
# Valide le flux complet avec de VRAIS JWT Clerk :
#   Clerk user (API Backend) -> Session -> JWT -> FastAPI
#   -> JWT Verification (JWKS réel) -> CurrentUser -> Provisioning
#   -> Internal User -> Role -> Thread Ownership -> Message -> SSE
#
# Règles :
#   - CLERK_SECRET_KEY lu depuis l'env, JAMAIS affiché
#   - aucun JWT / Bearer token affiché
#   - ne modifie AUCUN fichier de config ni la base
#   - crée des users Clerk de test (aucune suppression)
#   - la vérification JWT locale reflète le mécanisme serveur
#     (PyJWKClient officiel, RS256, issuer, exp) — jamais
#     verify_signature=False.
import json
import os
import sqlite3
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
from jwt import PyJWKClient

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

BASE = os.environ.get("E2E_BASE", "http://127.0.0.1:8000")
MODEL = os.environ.get("E2E_MODEL", "qwen2.5:1.5b")
TS = str(int(time.time()))[-6:]

SECRET = os.environ.get("CLERK_SECRET_KEY", "")
ISSUER = os.environ.get("CLERK_ISSUER", "")
JWKS = os.environ.get("CLERK_JWKS_URL", "") or f"{ISSUER}/.well-known/jwks.json"

results = []


def check(label, cond, detail=""):
    results.append((label, bool(cond)))
    print(
        f"[{'PASS' if cond else 'FAIL'}] {label}"
        + (f" -- {detail}" if detail else "")
    )


def mask(value: str) -> str:
    return value[:12] + "…" if value else "(vide)"


if not SECRET:
    print("ERREUR: CLERK_SECRET_KEY absent du backend/.env — abort")
    sys.exit(2)


UA = "clerk-e2e-validation/1.0 (+local-validation)"


def http_json(url, method="GET", data=None, token=None, timeout=60):
    headers = {"Content-Type": "application/json", "User-Agent": UA}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"__status__": e.code, "__body__": e.read().decode()[:300]}


def st(res):
    return res.get("__status__", 200) if isinstance(res, dict) else 200


def api(path, method="GET", data=None, token=None, timeout=60):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}", data=body, method=method, headers=headers
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"__status__": e.code, "__body__": e.read().decode()[:300]}


# ------------------------------------------------------------------
# 0. Environnement
# ------------------------------------------------------------------
print(f"== Environnement == BASE={BASE} ISSUER={ISSUER}")
check("ENV: issuer configuré", bool(ISSUER))
check("ENV: CLERK_SECRET_KEY présent (jamais affiché)", bool(SECRET))

# JWKS réel
try:
    client = PyJWKClient(JWKS, cache_keys=True)
    client.get_signing_keys()
    check("JWKS1: .well-known/jwks.json joignable + clés RS256", True)
except Exception as exc:
    check("JWKS1: .well-known/jwks.json joignable + clés RS256", False, str(exc)[:120])

# ------------------------------------------------------------------
# 1. Création de VRAIS users Clerk (équivalent SignUp API Backend)
# ------------------------------------------------------------------
print("\n== Provisioning Clerk (API Backend) ==")


def create_clerk_user(tag):
    # L'instance exige `username` comme identifiant (config dashboard).
    username = f"e2e-{tag}-{TS}"
    data = {
        "username": username,
        "email_address": [f"e2e-{tag}-{TS}@example.org"],
        "password": "E2e!Validation#2026",
        "first_name": f"E2E-{tag.upper()}",
    }
    res = http_json("https://api.clerk.com/v1/users", "POST", data=data, token=SECRET)
    if res.get("id"):
        return res
    print(f"  [WARN] création user {tag} échouée: {res.get('__body__')}")
    return res


def clerk_token(user_id):
    """Crée une session active + JWT via l'API Clerk."""
    s = http_json(
        "https://api.clerk.com/v1/sessions",
        "POST",
        data={"user_id": user_id},
        token=SECRET,
    )
    if s.get("token"):
        return s["token"], s.get("id")
    sid = s.get("id")
    if not sid:
        return None, None
    t = http_json(
        f"https://api.clerk.com/v1/sessions/{sid}/tokens",
        "POST",
        data={},
        token=SECRET,
    )
    return t.get("jwt") or t.get("token"), sid


user_a = create_clerk_user("usera")
user_b = create_clerk_user("userb")
a_ckid = user_a.get("id", "")
b_ckid = user_b.get("id", "")
check("CLERK1: user A créé (clerk_user_id)", bool(a_ckid))
check("CLERK2: user B créé (clerk_user_id)", bool(b_ckid))

tok_a, sid_a = clerk_token(a_ckid)
tok_b, sid_b = clerk_token(b_ckid)
check("CLERK3: session A créée (active)", bool(sid_a))
check("CLERK4: session B créée (active)", bool(sid_b))
check("CLERK5: JWT A obtenu (signature Clerk)", bool(tok_a))
check("CLERK6: JWT B obtenu (signature Clerk)", bool(tok_b))

if not (tok_a and tok_b):
    print("  JWT indisponibles — abort")
    sys.exit(2)

# ------------------------------------------------------------------
# 2. Vérification JWT LOCALE réelle (même mécanisme que le serveur)
# ------------------------------------------------------------------
print("\n== JWT Verification (PyJWKClient officiel) ==")


def verify(token):
    key = client.get_signing_key_from_jwt(token)
    for _ in range(2):
        try:
            return __import__("jwt").decode(
                token,
                key=key.key,
                algorithms=["RS256"],
                options={"require": ["exp", "sub", "iss"]},
                issuer=ISSUER,
            )
        except __import__("jwt").exceptions.ImmatureSignatureError as e:
            # Horloge locale en retard sur Clerk : attendre la maturité iat
            # (au plus une fois). Le serveur applique le même comportement
            # spec JWT — ce wait est propre au harness, pas au backend.
            import datetime as _dt

            now = time.time()
            payload = __import__("jwt").decode(
                token, options={"verify_signature": False}
            )
            wait = max(0.0, payload.get("iat", now) - now + 2.0)
            print(f"  [info] attente maturité JWT (skew horloge) {wait:.0f}s")
            time.sleep(wait)
    raise RuntimeError("JWT toujours immature après retry")


claims_a = verify(tok_a)
claims_b = verify(tok_b)
sub_a = claims_a["sub"]
sub_b = claims_b["sub"]
check("JWT1: signature + issuer + exp validés (A)", sub_a == a_ckid)
check("JWT2: signature + issuer + exp validés (B)", sub_b == b_ckid)
check("JWT3: sub == clerk_user_id (A)", sub_a == a_ckid)
check("JWT4: sub == clerk_user_id (B)", sub_b == b_ckid)
check("JWT5: exp futur (A)", claims_a["exp"] > time.time())

# ------------------------------------------------------------------
# 3. API : négatifs auth + protection des endpoints
# ------------------------------------------------------------------
print("\n== FastAPI : protection des endpoints ==")
r = api("/api/users/me")
check("AUTH1: sans token /users/me -> 401", st(r) == 401)
r = api("/api/users/me", token="invalid-token-xyz")
check("AUTH2: token invalide /users/me -> 401", st(r) == 401)
r = api("/api/threads/00000000-0000-0000-0000-000000000000")
check("AUTH3: sans token GET thread -> 401 (avant 404)", st(r) == 401)

# ------------------------------------------------------------------
# 4. CurrentUser + Provisioning + Internal User
# ------------------------------------------------------------------
print("\n== CurrentUser + Provisioning ==")
me_a1 = api("/api/users/me", token=tok_a)
me_a2 = api("/api/users/me", token=tok_a)
check(
    "PROV1: premier appel authentifié -> 200 (provisioning)",
    st(me_a1) == 200,
)
check(
    "PROV2: mapping clerk_user_id -> internal (A)",
    me_a1.get("clerk_user_id") == sub_a and bool(me_a1.get("user_id")),
)
int_a = me_a1.get("user_id", "")
check("PROV3: user interne UUID", len(int_a) == 36)
check(
    "PROV4: stable à la 2e requête (pas de nouvel UUID)",
    me_a2.get("user_id") == int_a,
)

me_b = api("/api/users/me", token=tok_b)
int_b = me_b.get("user_id", "")
check(
    "PROV5: mapping distinct A ≠ B (isolation identity)",
    bool(int_b) and int_b != int_a,
)

# ------------------------------------------------------------------
# 5. Role
# ------------------------------------------------------------------
print("\n== Role ==")
check("ROLE1: user hors ADMIN_CLERK_IDS -> role 'user' (A)", me_a1.get("role") == "user")
check("ROLE2: user hors ADMIN_CLERK_IDS -> role 'user' (B)", me_b.get("role") == "user")

# ADMIN_CLERK_IDS -> admin : même fonction de résolution, en mémoire.
from app import config as cfg
from app.auth import resolver as res

_orig_admins = list(cfg.ADMIN_CLERK_IDS)
res.ADMIN_CLERK_IDS = cfg.ADMIN_CLERK_IDS = [sub_a]
try:
    admin_user = res.resolve_internal_user(sub_a, "E2E Admin")
    check("ROLE3: ADMIN_CLERK_IDS contient sub A -> role 'admin'", admin_user.role == "admin")
finally:
    res.ADMIN_CLERK_IDS = cfg.ADMIN_CLERK_IDS = _orig_admins

# ------------------------------------------------------------------
# 6. Thread — ownership
# ------------------------------------------------------------------
print("\n== Thread Ownership ==")
th_a = api(
    f"/api/users/{int_a}/threads",
    "POST",
    data={"name": "E2E-A"},
    token=tok_a,
)
check("OWN1: A crée son thread -> 201", st(th_a) == 201, th_a.get("user_id", ""))
tid = th_a.get("thread_id", "")
check("OWN2: thread lié à user interne A", th_a.get("user_id") == int_a)

r = api(f"/api/threads/{tid}", token=tok_a)
check("OWN3: A GET son thread -> 200", st(r) == 200)
r = api(f"/api/threads/{tid}", token=tok_b)
check("OWN4: B GET thread A -> 403", st(r) == 403, r.get("__body__", ""))
r = api(f"/api/threads/{tid}", "PUT", data={"name": "hack"}, token=tok_b)
check("OWN5: B RENAME thread A -> 403", st(r) == 403)
r = api(f"/api/threads/{tid}/state", token=tok_b)
check("OWN6: B GET state thread A (sans user_id) -> 403", st(r) == 403)
r = api(f"/api/threads/{tid}/state?user_id={int_b}", token=tok_b)
check("OWN7: B GET state thread A (user_id B) -> 403", st(r) == 403)
r = api(f"/api/threads/{tid}/history", token=tok_b)
check("OWN8: B GET history thread A -> 403", st(r) == 403)
r = api(f"/api/threads/{tid}/activity?user_id={int_b}", token=tok_b)
check("OWN9: B GET activity thread A -> 403", st(r) == 403)
r = api(
    "/api/chat",
    "POST",
    data={"user_id": int_a, "thread_id": tid, "message": "hello"},
    token=tok_b,
)
check("OWN10: B chat sur thread A (usurpation user_id) -> 403", st(r) == 403)
r = api(f"/api/users/{int_a}/threads", token=tok_b)
check("OWN11: B liste threads A -> 404 (anti-énumération)", st(r) == 404)
r = api(f"/api/users/{int_b}/threads", token=tok_b)
check("OWN12: B liste SES threads -> 200 vide", st(r) == 200)

# ------------------------------------------------------------------
# 7. Message (POST /api/chat — user A, OWN thread)
# ------------------------------------------------------------------
print("\n== Message ==")
r = api(
    "/api/chat",
    "POST",
    data={
        "user_id": int_a,
        "thread_id": tid,
        "message": "Devinette : 7 × 6 ?",
        "model": MODEL,
    },
    token=tok_a,
    timeout=240,
)
check(
    "MSG1: A chat sur SON thread -> 200",
    st(r) == 200 and len(r.get("response", "")) > 0,
    (r.get("response") or r.get("__body__", ""))[:60],
)
r = api(f"/api/threads/{tid}/state", token=tok_a)
check(
    "MSG2: state persiste le message (checkpoint)",
    st(r) == 200
    and any(m.get("type") == "HumanMessage" for m in r.get("messages", [])),
)

# ------------------------------------------------------------------
# 8. SSE — token transmis en header
# ------------------------------------------------------------------
print("\n== SSE ==")


def sse_stream(token, params, timeout=240):
    url = (
        f"{BASE}/api/chat/stream?user_id={params['user_id']}"
        f"&thread_id={params['thread_id']}&message={params['message']}"
        f"&model={MODEL}"
    )
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode(errors="replace")
            return True, body
    except urllib.error.HTTPError as e:
        return False, e.read().decode(errors="replace")[:200]
    except Exception as e:
        return False, str(e)[:200]


ok, body = sse_stream(tok_a, {"user_id": int_a, "thread_id": tid, "message": "Suite"})
ev_types = [l.split(": ", 1)[1] for l in body.splitlines() if l.startswith("event: ")]
check(
    "SSE1: stream authentifié (JWT header) -> événements",
    ok and "event:" in body,
    ",".join(ev_types[:6]),
)
ok_bad, body_bad = sse_stream(
    "invalid-sse-token", {"user_id": int_a, "thread_id": tid, "message": "x"}
)
check("SSE2: stream token invalide -> 401 (ou erreur avant events)", not ok_bad or ("RUN_END" not in body_bad), body_bad[:60])

# ------------------------------------------------------------------
# 9. Isolation mémoire / profil
# ------------------------------------------------------------------
print("\n== Isolation (User A ≠ User B) ==")
r = api(f"/api/users/{int_b}/memory/facts", token=tok_a)
check("ISO1: A lit memory B -> 403", st(r) == 403)
r = api(f"/api/users/{int_b}/memory/facts", "POST",
        data={"category": "preference", "content": "hack"}, token=tok_a)
check("ISO2: A écrit memory B -> 403", st(r) == 403)
r = api(f"/api/users/{int_b}/profile", token=tok_a)
check("ISO3: A lit profile B -> 403", st(r) == 403)
r = api(f"/api/users/{int_a}/memory", token=tok_a)
check("ISO4: A lit SA memory -> 200", st(r) == 200)
r = api(f"/api/users/{int_a}/threads", token=tok_a)
check("ISO5: A liste SES threads -> 200 (≥1)", st(r) == 200 and len(r) >= 1)

# ------------------------------------------------------------------
# Résultat
# ------------------------------------------------------------------
fails = [label for label, ok in results if not ok]
print(f"\n===== {len(results) - len(fails)}/{len(results)} PASS =====")
if fails:
    print("FAILS:", fails)
    sys.exit(1)