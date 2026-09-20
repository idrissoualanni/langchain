# Mission Identité — tests sécurité backend (§24)
# Sans token → 401 | token invalide → 401 | token valide → accès
# Ownership : B sur thread/memory/learning/profile de A → 403
# Admin : user → admin route → 403 ; admin → 200
# SSE : token valide/invalide
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, ".")

BASE = f"http://127.0.0.1:{os.environ.get('BASE_PORT', '8001')}"

results = []


def check(label, cond, detail=""):
    results.append((label, bool(cond)))
    print(
        f"[{'PASS' if cond else 'FAIL'}] {label}"
        + (f" -- {detail}" if detail else "")
    )


def api(path, method="GET", body=None, token=None, raw=False,
        timeout=60):
    data = (
        json.dumps(body).encode() if body is not None else None
    )
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, method=method, headers=headers
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read().decode()
            return json.loads(payload) if not raw else payload
    except urllib.error.HTTPError as e:
        return {"__status__": e.code, "__body__": e.read().decode()[:200]}


def status(res):
    return res.get("__status__", 200) if isinstance(res, dict) else 200


# ---------- 1. AUTHENTIFICATION ----------
r = api("/api/users/me")
check(
    "AUTH1: sans token /users/me → 401",
    status(r) == 401,
    str(r)[:80],
)

r = api("/api/users/me", token="invalid-token-xyz")
check(
    "AUTH2: token invalide /users/me → 401",
    status(r) == 401,
    str(r)[:80],
)

r = api("/api/threads/00000000-0000-0000-0000-000000000000")
check(
    "AUTH3: sans token GET thread → 401 (avant 404)",
    status(r) == 401,
)

# ---------- 2. PROVISIONING + SESSION ( mode dev ) ----------
ua = api("/api/users", "POST", {"name": "Secu-A"})
ub = api("/api/users", "POST", {"name": "Secu-B"})
ta_a = ua["dev_token"]
ta_b = ub["dev_token"]
check(
    "PROV1: users de test provisionnes (dev tokens)",
    ta_a.startswith("dev:") and ta_b.startswith("dev:"),
    f"A={ua['user_id'][:8]} B={ub['user_id'][:8]}",
)

me = api("/api/users/me", token=ta_a)
check(
    "PROV2: /users/me renvoie le user de la SESSION",
    me.get("user_id") == ua["user_id"],
    me.get("name", ""),
)

# ---------- 3. OWNERSHIP THREADS ----------
th_a = api(
    f"/api/users/{ua['user_id']}/threads",
    "POST",
    {"name": "thread-A"},
    token=ta_a,
)
check(
    "OWN1: A cree son thread",
    "thread_id" in th_a,
    str(th_a)[:80],
)

tid = th_a["thread_id"]

r = api(
    f"/api/users/{ub['user_id']}/threads", "POST", {"name": "x"},
    token=ta_b,
)
# B cree pour B : OK ; testons B qui tente le thread de A
r = api(f"/api/threads/{tid}", token=ta_b)
check(
    "OWN2: B GET thread A → 403",
    status(r) == 403,
    str(r)[:80],
)

r = api(
    f"/api/threads/{tid}", "PUT", {"name": "hack"},
    token=ta_b,
)
check(
    "OWN3: B RENAME thread A → 403",
    status(r) == 403,
)

r = api(f"/api/threads/{tid}/state", token=ta_b)
check(
    "OWN4: B GET state thread A (SANS user_id) → 403 (bypass ferme)",
    status(r) == 403,
)

r = api(
    f"/api/threads/{tid}/state?user_id={ub['user_id']}", token=ta_b
)
check(
    "OWN5: B GET state thread A (user_id B) → 403",
    status(r) == 403,
)

r = api(f"/api/threads/{tid}/history", token=ta_b)
check(
    "OWN6: B GET history thread A → 403",
    status(r) == 403,
)

r = api(
    f"/api/threads/{tid}/activity?user_id={ub['user_id']}",
    token=ta_b,
)
check(
    "OWN7: B GET activity thread A → 403",
    status(r) == 403,
)

r = api(
    "/api/chat",
    "POST",
    {
        "user_id": ua["user_id"],
        "thread_id": tid,
        "message": "hello",
    },
    token=ta_b,
)
check(
    "OWN8: B chat sur thread A (usurpation user_id) → 403",
    status(r) == 403,
)

# A utilise son propre thread → 200 ( run LLM : timeout long )
r = api(
    "/api/chat",
    "POST",
    {
        "user_id": ua["user_id"],
        "thread_id": tid,
        "message": "Bonjour !",
    },
    token=ta_a,
    timeout=300,
)
check(
    "OWN9: A chat sur SON thread → 200",
    status(r) == 200 and len(r.get("response", "")) > 0,
    str(r.get("response", ""))[:60],
)

# ---------- 4. OWNERSHIP MEMORY / LEARNING / LIST ----------
r = api(
    f"/api/users/{ub['user_id']}/memory/facts", token=ta_a
)
check(
    "OWN10: A lit memory B → 403",
    status(r) == 403,
)

r = api(
    f"/api/users/{ub['user_id']}/memory/facts",
    "POST",
    {"category": "preference", "content": "hack"},
    token=ta_a,
)
check(
    "OWN11: A ecrit memory B → 403",
    status(r) == 403,
)

r = api(
    f"/api/users/{ub['user_id']}/profile", token=ta_a
)
check(
    "OWN12: A lit profile B → 403",
    status(r) == 403,
)

r = api(f"/api/learning/{ub['user_id']}/profile", token=ta_a)
check(
    "OWN13: A lit learning B → 403",
    status(r) == 403,
)

r = api(
    f"/api/learning/{ub['user_id']}/observations", token=ta_a
)
check(
    "OWN14: A lit observations B → 403",
    status(r) == 403,
)

r = api(
    f"/api/users/{ub['user_id']}/threads", token=ta_a
)
check(
    "OWN15: A liste threads B → 404 (anti-enumeration)",
    status(r) == 404,
)

# A lit SA memory → 200
r = api(
    f"/api/users/{ua['user_id']}/memory", token=ta_a
)
check(
    "OWN16: A lit SA memory → 200",
    status(r) == 200,
)

r = api(
    f"/api/users/{ua['user_id']}/threads", token=ta_a
)
check(
    "OWN17: A liste SES threads → 200",
    status(r) == 200 and len(r) >= 1,
)

# ---------- 5. ADMIN ----------
r = api("/api/logs", token=ta_a)
check(
    "ADM1: user → /api/logs → 403",
    status(r) == 403,
)

r = api("/api/users", token=ta_a)
check(
    "ADM2: user → list users → 403",
    status(r) == 403,
)

# admin via ADMIN_CLERK_IDS=dev-admin
r = api("/api/logs?limit=5", token="dev:admin")
check(
    "ADM3: admin → /api/logs → 200",
    status(r) == 200,
)

r = api("/api/users", token="dev:admin")
check(
    "ADM4: admin → list users → 200",
    status(r) == 200 and len(r) >= 2,
)

# ---------- 6. SSE ----------
req = urllib.request.Request(
    f"{BASE}/api/chat/stream?user_id={ua['user_id']}"
    f"&thread_id={tid}&message=test",
    headers={"Authorization": f"Bearer {ta_a}"},
)
try:
    with urllib.request.urlopen(req, timeout=90) as resp:
        body = resp.read(2000).decode(errors="replace")
        sse_ok = "event:" in body
except urllib.error.HTTPError as e:
    body = e.read().decode()[:200]
    sse_ok = False
check(
    "SSE1: stream authentifie (token valide) → evenements",
    sse_ok,
    body[:80],
)

req = urllib.request.Request(
    f"{BASE}/api/chat/stream?user_id={ua['user_id']}"
    f"&thread_id={tid}&message=test",
    headers={"Authorization": "Bearer invalid-sse"},
)
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read(500).decode(errors="replace")
        sse_bad = False
except urllib.error.HTTPError as e:
    sse_bad = e.code == 401
check(
    "SSE2: stream token invalide → 401",
    sse_bad,
)

# ---------- RESULTAT ----------
fails = [label for label, ok in results if not ok]
print(f"\n===== {len(results) - len(fails)}/{len(results)} PASS =====")
if fails:
    print("FAILS:", fails)
    sys.exit(1)
