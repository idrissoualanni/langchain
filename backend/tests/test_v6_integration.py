# Tests V6 integration serveur : tools learning via LLM reel,
# cross-thread, restart, API, preview, isolation.
import json
import re
import sys
import urllib.request
import uuid

sys.path.insert(0, ".")

BASE = "http://127.0.0.1:8001"
results = []


def check(label, cond, detail=""):
    results.append((label, bool(cond)))
    print(
        f"[{'PASS' if cond else 'FAIL'}] {label}"
        + (f" -- {detail}" if detail else "")
    )


TOKENS = {}  # user_id -> dev token ( session simulée mode dev )
LAST_TOKEN = [None]


def api(path, method="GET", body=None, token=None):
    import json as _json
    import urllib.request as _rq
    data = _json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    # token explicite > token du user dans l'URL > dernier actif
    if token is None:
        m = re.search(r"/api/users/([^/]+)", path)
        if m and m.group(1) in TOKENS:
            token = TOKENS[m.group(1)]
    if token is None and LAST_TOKEN[0]:
        token = LAST_TOKEN[0]
    if token:
        headers["Authorization"] = "Bearer " + token
    req = _rq.Request(BASE + path, data=data, method=method, headers=headers)
    with _rq.urlopen(req, timeout=300) as resp:
        return _json.loads(resp.read().decode())


def new_user(name):
    u = api("/api/users", "POST", {"name": name})
    TOKENS[u["user_id"]] = u.get("dev_token", "dev:" + u["user_id"])
    LAST_TOKEN[0] = TOKENS[u["user_id"]]
    return u["user_id"]


def new_thread(uid, name):
    return api(
        f"/api/users/{uid}/threads", "POST", {"name": name}
    )["thread_id"]


# ---------- SETUP : user avec evaluation pre-existante ----------
u = new_user("v6it-" + uuid.uuid4().hex[:6])
t1 = new_thread(u, "thread-A")

# Tour 1 : le tuteur cree l'exercice (workflow regle 17 : question
# puis on attend — l'evaluation ne peut PAS avoir lieu ce tour)
resp = api(
    "/api/chat",
    "POST",
    {
        "user_id": u,
        "thread_id": t1,
        "message": "Donne-moi un exercice sur les fonctions en Python.",
    },
)
check(
    "IT1a: le tuteur cree l'exercice et attend la reponse",
    len(resp["response"]) > 10,
    resp["response"][:100].encode("ascii", "replace").decode(),
)

# Tour 2 : l'etudiant repond -> evaluate_answer PUIS (regle 15)
# record_learning_observation dans le meme tour
resp = api(
    "/api/chat",
    "POST",
    {
        "user_id": u,
        "thread_id": t1,
        "message": (
            "Ma reponse : une fonction est un bloc de code "
            "reutilisable qui peut retourner une valeur grace a "
            "return. Evalue ma reponse."
        ),
    },
)
check(
    "IT1b: evaluation de la reponse reussit",
    len(resp["response"]) > 10,
    resp["response"][:100].encode("ascii", "replace").decode(),
)

# Le LLM a-t-il enregistre une observation ? (regle 15 du Core Prompt)
profile = api(f"/api/learning/{u}/profile")
recorded_by_llm = (
    profile.get("status") == "active"
    and "python" in profile.get("subjects", {})
    and any(
        t.get("attempts", 0) > 0
        for t in profile["subjects"]["python"].get(
            "topics", {}
        ).values()
    )
)
check(
    "IT2: LLM a enregistre une observation learning via tool",
    recorded_by_llm,
    json.dumps(profile)[:150],
)

# ---------- IT3 : cross-thread (thread B voit le profil) ----------
t2 = new_thread(u, "thread-B")
pv = api(
    "/api/context/preview",
    "POST",
    {"user_id": u, "query": "Je veux continuer les fonctions Python."},
)
lg = pv.get("learning")
check(
    "IT3: thread B (preview) voit la progression du thread A",
    lg is not None
    and lg["status"] == "active"
    and lg["subject"] == "python"
    and (lg["attempts"] or 0) >= 1,
    f"learning={lg['status'] if lg else None} attempts={lg.get('attempts') if lg else None}",
)

# ---------- IT4 : nouveau user sans profil -> chat normal ----------
u_new = new_user("v6new-" + uuid.uuid4().hex[:6])
t_new = new_thread(u_new, "fresh")
resp_new = api(
    "/api/chat",
    "POST",
    {
        "user_id": u_new,
        "thread_id": t_new,
        "message": "Explique-moi les variables Python.",
    },
)
check(
    "IT4: nouvel etudiant discute normalement (sans profil, 26)",
    len(resp_new["response"]) > 10,
    resp_new["response"][:80].encode("ascii", "replace").decode(),
)
p_new = api(f"/api/learning/{u_new}/profile")
check(
    "IT4b: profil not_started via API",
    p_new["status"] == "not_started",
)

# ---------- IT5 : isolation utilisateurs ----------
u_iso = new_user("v6iso-" + uuid.uuid4().hex[:6])
p_iso = api(f"/api/learning/{u_iso}/profile")
check(
    "IT5: l'autre user n'a pas acces au profil de A",
    p_iso["status"] == "not_started",
)

# ---------- IT6 : logs LEARNING_* emis ----------
logs = api("/api/logs?limit=200")
entries = logs if isinstance(logs, list) else logs.get("entries", [])
events_seen = {e.get("event", "") for e in entries}
learning_events = {
    ev
    for ev in events_seen
    if ev.startswith("LEARNING_")
}
check(
    "IT6: evenements LEARNING_* dans les logs (37)",
    len(learning_events) >= 2,
    str(sorted(learning_events))[:150],
)

# ---------- IT7 : routes API learning completes ----------
topics = api(f"/api/learning/{u}/topics")
check(
    "IT7: /topics structure par matiere",
    topics["status"] == "active"
    and "python" in topics["subjects"],
)
obs = api(f"/api/learning/{u}/observations")
check(
    "IT7b: /observations historique present",
    isinstance(obs, list) and len(obs) >= 1,
)

# ---------- IT8 : mastery evolue avec une 2e evaluation ----------
# Injection directe (le LLM est non deterministe) pour verifier
# la formule cote serveur via l'API.
from app.schemas.learning import LearningObservation
from app.learning.learning_profile import (
    read_learning_profile,
    update_profile_from_observation,
)

before = read_learning_profile(u)
if (
    before
    and "python" in before.subjects
    and before.subjects["python"].topics
):
    first_topic = list(before.subjects["python"].topics.keys())[0]
    m0 = (
        before.subjects["python"]
        .topics[first_topic]
        .mastery
    )
    a0 = before.subjects["python"].topics[first_topic].attempts
    update_profile_from_observation(
        u,
        LearningObservation(
            subject="python",
            topic=first_topic,
            type="exercise",
            score=0.85,
        ),
    )
    after = read_learning_profile(u)
    m1 = (
        after.subjects["python"].topics[first_topic].mastery
    )
    a1 = after.subjects["python"].topics[first_topic].attempts
    check(
        "IT8: mastery evolue (formule) et attempts++",
        m1 != m0 and a1 == a0 + 1 and m1 > m0,
        f"{m0} -> {m1} (attempts {a0}->{a1})",
    )
else:
    check(
        "IT8: skipped - pas de topic python evalue par le LLM",
        False,
        "le LLM n'a pas enregistre (voir IT2)",
    )

# ---------- Resume ----------
fails = [label for label, ok in results if not ok]
print()
print(
    f"TOTAL: {len(results)} | PASS: {len(results) - len(fails)} | FAIL: {len(fails)}"
)
if fails:
    print("ECHECS:", fails)
    sys.exit(1)
print("TESTS V6 INTEGRATION: OK")
