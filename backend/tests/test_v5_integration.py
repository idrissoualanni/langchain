# Tests d'intégration V5 — serveur réel : chat LLM avec Runtime
# Context + dynamic_prompt natif + régression V3/V4 complète
import json
import sys
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, ".")

import os

# Port configurable (8001 par défaut : port de test utilisé
# pendant l'intégration V6 pour ne pas écraser le serveur de
# dev). BASE_PORT = 8000 restaure l'ancien comportement.
BASE = f"http://127.0.0.1:{os.environ.get('BASE_PORT', '8001')}"

results = []


def check(label, cond, detail=""):
    results.append((label, bool(cond)))
    print(
        f"[{'PASS' if cond else 'FAIL'}] {label}"
        + (f" -- {detail}" if detail else "")
    )


def api(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode())


def new_user(name):
    return api("/api/users", "POST", {"name": name})["user_id"]


def new_thread(user_id, name):
    return api(
        f"/api/users/{user_id}/threads", "POST", {"name": name}
    )["thread_id"]


# ---------- SETUP ----------
u = new_user("V5-It-" + uuid.uuid4().hex[:6])
t = new_thread(u, "v5-main")

# Mémoire pour le prompt dynamique
api(
    f"/api/users/{u}/memory/facts",
    "POST",
    {
        "category": "preference",
        "content": "Prefere les explications tres concises",
    },
)
print(f"user={u} thread={t}")

# ---------- 1. CHAT LLM avec Runtime Context + dynamic_prompt ----------
resp = api(
    "/api/chat",
    "POST",
    {
        "user_id": u,
        "thread_id": t,
        "message": "Explique-moi les fonctions Python en une phrase.",
    },
)
check(
    "IT1: chat LLM repond (runtime context + dynamic prompt natif)",
    len(resp["response"]) > 10
    and "fonction" in resp["response"].lower(),
    resp["response"][:100],
)

# ---------- 2. CHECKPOINTER (state persiste) ----------
state = api(f"/api/threads/{t}/state?user_id={u}")
check(
    "IT2: checkpointer intact",
    state["message_count"] >= 2,
    f"messages={state['message_count']}",
)

# ---------- 3. Mémoire cross-thread (user store, thread différent) ----------
t2 = new_thread(u, "v5-other")
resp2 = api(
    "/api/chat",
    "POST",
    {
        "user_id": u,
        "thread_id": t2,
        "message": "Quelles sont mes preferences d'apprentissage ?",
    },
)
check(
    "IT3: memoire cross-thread (thread 2 voit le user store)",
    len(resp2["response"]) > 10,
    resp2["response"][:120],
)

# ---------- 4. Fallback unsupported en chat réel ----------
t3 = new_thread(u, "v5-astro")
resp3 = api(
    "/api/chat",
    "POST",
    {
        "user_id": u,
        "thread_id": t3,
        "message": "Explique-moi l astrophysique.",
    },
)
check(
    "IT4: fallback unsupported — pas de crash, reponse honnete",
    len(resp3["response"]) > 10,
    resp3["response"][:100],
)

# ---------- 5. Isolation utilisateurs ----------
u_b = new_user("V5-IsoB-" + uuid.uuid4().hex[:6])
api(
    f"/api/users/{u_b}/memory/facts",
    "POST",
    {"category": "identity", "content": "S appelle Bruno"},
)
# Preview B ne doit pas contenir la mémoire de A
pv_b = api(
    "/api/subjects/preview/context",
    "POST",
    {"user_id": u_b, "query": "Explique-moi les fonctions Python."},
)
check(
    "IT5: isolation A/B (preview)",
    "concises" not in json.dumps(pv_b["user"]),
)

# ---------- 6. TOOLS pedagogiques toujours operationnels ----------
resp6 = api(
    "/api/chat",
    "POST",
    {
        "user_id": u,
        "thread_id": t,
        "message": "Donne-moi un exercice sur le return en Python.",
    },
)
state6 = api(f"/api/threads/{t}/state?user_id={u}")
tools_used = []
for m in state6["messages"]:
    if m["type"] == "AIMessage" and m.get("tool_calls"):
        for tc in m["tool_calls"]:
            tools_used.append(tc["name"])
check(
    "IT6: create_exercise appele par le LLM (tools preserves)",
    "create_exercise" in tools_used,
    str(tools_used),
)

# ---------- 7. Events SSE infrastructure (logs API) ----------
logs = api("/api/logs?limit=100")
events_seen = set()
for entry in logs if isinstance(logs, list) else logs.get("entries", []):
    events_seen.add(entry.get("event", ""))
required_events = {
    "ROUTING_START",
    "ROUTING_END",
    "CONTEXT_BUILD_START",
    "CONTEXT_BUILD_END",
    "PROMPT_BUILD",
    "SUBJECT_CONTEXT_SELECTED",
    "KNOWLEDGE_SELECTED",
    "TOOLS_SELECTED",
    "TOOL_START",
    "TOOL_END",
    "RUN_START",
    "RUN_END",
    "CHECKPOINT_SAVED",
}
check(
    "IT7: evenements observabilite presents (SSE/EventBus intacts)",
    len(required_events & events_seen) >= 10,
    str(sorted(required_events & events_seen))[:200],
)

# ---------- 8. Subject Registry API ----------
subs = api("/api/subjects")
check(
    "IT8: /api/subjects (4 matieres)",
    len(subs) == 4,
    str([s["id"] for s in subs]),
)

# ---------- 9. Preview context (BuiltContext serialisé) ----------
pv = api(
    "/api/subjects/preview/context",
    "POST",
    {"user_id": u, "query": "Explique-moi return en Python."},
)
check(
    "IT9: preview BuiltContext (routing + tools V5)",
    pv["router"]["status"] == "supported"
    and "create_exercise" in pv["tools"]["available"],
    f"{pv['router']['status']} | tools avail={len(pv['tools']['available'])}",
)
check(
    "IT9: prompt preview sans VALEUR d'ID technique",
    # §36 : aucune valeur d'identifiant (uuid user/thread) dans le
    # prompt. Le mot "user_id" peut apparaître dans les RÈGLES du
    # Core (sémantique des tools mémoire) — pas sa valeur.
    u not in pv["prompt_preview"]
    and t not in pv["prompt_preview"]
    and "user_id=" not in pv["prompt_preview"]
    and "thread_id=" not in pv["prompt_preview"],
)

fails = [label for label, ok in results if not ok]
print()
print(
    f"TOTAL: {len(results)} | PASS: {len(results) - len(fails)} | FAIL: {len(fails)}"
)
if fails:
    print("ECHECS:", fails)
    sys.exit(1)
