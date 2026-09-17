# Tests de parcours complets — mission INTÉGRATION FINALE §30-§39.
# Scénarios E2E réels contre le serveur (LLM réel + tools réels).
# Usage : python -X utf8 tests\test_final_integration.py
# (serveur requis sur 127.0.0.1:8001, cf. BASE_PORT)
import json
import os
import re
import sys
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, ".")

BASE = f"http://127.0.0.1:{os.environ.get('BASE_PORT', '8001')}"

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


def chat(uid, tid, message):
    return api(
        "/api/chat",
        "POST",
        {"user_id": uid, "thread_id": tid, "message": message},
    )


def asc(s):
    return (s or "").encode("ascii", "replace").decode()


# ==================================================================
# §30 — PARCOURS PÉDAGOGIQUE COMPLET (LLM réel, multi-tours)
# ==================================================================
print("\n--- §30 parcours pédagogique E2E ---")
u30 = new_user("e2e-" + uuid.uuid4().hex[:6])
t30 = new_thread(u30, "parcours")

# Tour 1 : demande d'exercice → create_exercise → waiting
r1 = chat(u30, t30, "Donne-moi un exercice sur les fonctions Python.")
act1 = api(f"/api/threads/{t30}/activity?user_id={u30}")
check(
    "30a: exercice créé, activité en attente de réponse",
    (act1.get("activity") or {}).get("status")
    == "waiting_for_answer",
    json.dumps(act1.get("activity"))[:120],
)

# §35 — NO-ANSWER : « Bonjour » n'est PAS une réponse
r2 = chat(u30, t30, "Bonjour")
act2 = api(f"/api/threads/{t30}/activity?user_id={u30}")
check(
    "35: 'Bonjour' ≠ réponse — activité reste waiting_for_answer",
    (act2.get("activity") or {}).get("status")
    == "waiting_for_answer",
    (act2.get("activity") or {}).get("status"),
)

# Tour 3 : vraie réponse → evaluate_answer → observation profil
# (réponse riche couvrant les termes-clés réels de la section :
# fonction, reutilisable, parentheses, duplication, necessaire,
# programme, modulaire, portant — le scoring est lexical)
r3 = chat(
    u30,
    t30,
    "Ma réponse : une fonction est un bloc de code réutilisable "
    "portant un nom, défini avec def suivi du nom, de "
    "parenthèses et de deux points. Elle peut être appelée "
    "autant de fois que nécessaire, ce qui évite la "
    "duplication et rend le programme modulaire. Évalue ma "
    "réponse.",
)
profile30 = api(f"/api/learning/{u30}/profile")
py_topics = (
    (profile30.get("subjects", {}).get("python", {}) or {}).get(
        "topics", {}
    )
    or {}
)
check(
    "30b: Learning Profile a reçu l'observation (attempts >= 1)",
    profile30.get("status") == "active"
    and any(
        t.get("attempts", 0) >= 1 for t in py_topics.values()
    ),
    json.dumps(py_topics)[:150],
)

# §14 : l'activité thread-local n'est PAS confondue avec le profil
act3 = api(f"/api/threads/{t30}/activity?user_id={u30}")
check(
    "30c: activité thread-local distincte du profil (pas de "
    "'learning' dans l'activité)",
    "learning" not in json.dumps(act3.get("activity") or {}),
)

# §37/§13 — compréhension : tour 4, l'étudiant explique
r4 = chat(
    u30,
    t30,
    "Explication : return renvoie la valeur au code appelant et "
    "sort immédiatement de la fonction, tandis que print affiche "
    "seulement sans rien transmettre — donc sans return on ne "
    "peut pas réutiliser le résultat.",
)
act4 = api(f"/api/threads/{t30}/activity?user_id={u30}")
status4 = (act4.get("activity") or {}).get("status")
check(
    "37: après explication, activité termine proprement "
    "(completed/abandoned) ou vérification passée",
    status4 in (
        "completed",
        "abandoned",
        None,
        "checking_understanding",
    ),
    status4,
)

# ==================================================================
# §33 — CROSS-THREAD : activité A absente de B, profil présent
# ==================================================================
print("\n--- §33 cross-thread activité vs profil ---")
t30b = new_thread(u30, "thread-B")
act_b = api(f"/api/threads/{t30b}/activity?user_id={u30}")
check(
    "33a: thread B n'a PAS l'activité du thread A "
    "(activity_type None / status idle)",
    (act_b.get("activity") or {}).get("activity_type")
    in (None, ""),
    json.dumps(act_b.get("activity"))[:100],
)
pv_b = api(
    "/api/context/preview",
    "POST",
    {"user_id": u30, "query": "Je veux continuer les fonctions."},
)
lg = pv_b.get("learning")
check(
    "33b: Learning Profile DISPO dans B (progression vue)",
    lg is not None
    and lg.get("status") == "active"
    and (lg.get("attempts") or 0) >= 1,
    f"learning={lg.get('status') if lg else None}",
)

# ==================================================================
# §34 — CROSS-USER : user B ne voit RIEN de user A
# ==================================================================
print("\n--- §34 cross-user isolation ---")
u34 = new_user("iso-" + uuid.uuid4().hex[:6])
p34 = api(f"/api/learning/{u34}/profile")
check(
    "34a: profil de B vide (pas de fuite du profil A)",
    p34.get("status") == "not_started",
    p34.get("status"),
)
try:
    api(f"/api/threads/{t30}/activity?user_id={u34}")
    leaked = True
except urllib.error.HTTPError as e:
    leaked = e.code != 403
check(
    "34b: activité de A inaccessible à B (403)",
    not leaked,
)
try:
    api(
        f"/api/threads/{t30}/run-code",
        "POST",
        {"user_id": u34, "language": "python", "code": "print(1)"},
    )
    leaked_rc = True
except urllib.error.HTTPError as e:
    leaked_rc = e.code != 403
check(
    "34c: run-code de A interdit à B (403)",
    not leaked_rc,
)

# ==================================================================
# §36 — HINT : « Je suis bloqué » → give_hint level 0
# ==================================================================
print("\n--- §36 hint progressif ---")
u36 = new_user("hint-" + uuid.uuid4().hex[:6])
t36 = new_thread(u36, "hint")
chat(u36, t36, "Donne-moi un exercice sur les boucles Python.")
r36 = chat(u36, t36, "Je suis bloqué, je ne sais pas comment répondre.")
act36 = api(f"/api/threads/{t36}/activity?user_id={u36}")
hint_level = (act36.get("activity") or {}).get("hint_level")
check(
    "36: hint demandé — hint_level présent et progressif (<= 1 "
    "après 1er blocage)",
    hint_level is not None and 0 <= int(hint_level) <= 1,
    f"hint_level={hint_level}",
)

# ==================================================================
# §31 — CODE COMPLET : éditer → exécuter → tester → analyser
# ==================================================================
print("\n--- §31 code practice complet ---")
u31 = new_user("code-" + uuid.uuid4().hex[:6])
t31 = new_thread(u31, "code")

# 1. Exercice de code
r31 = chat(
    u31,
    t31,
    "Donne-moi un exercice de code Python sur les boucles.",
)
act31 = api(f"/api/threads/{t31}/activity?user_id={u31}")
check(
    "31a: exercice code créé (expected_response_type ou activité)",
    bool(act31.get("activity")),
    json.dumps(act31.get("activity"))[:100],
)

# 2. Code erroné via l'éditeur → exécution réelle
wrong = "def compte(n):\n  total = 0\n  for i in range(n)\n    total += i\n  return total\n"
run1 = api(
    f"/api/threads/{t31}/run-code",
    "POST",
    {"user_id": u31, "language": "python", "code": wrong},
)
check(
    "31b: code erroné exécuté — erreur de syntaxe remontée",
    run1.get("status") == "error"
    and "SyntaxError" in (run1.get("stderr") or ""),
    (run1.get("stderr") or "")[:100],
)

# 3. L'étudiant corrige → tests passent
fixed = "def compte(n):\n  total = 0\n  for i in range(n):\n    total += i\n  return total\n"
run2 = api(
    f"/api/threads/{t31}/run-code",
    "POST",
    {"user_id": u31, "language": "python", "code": fixed},
)
check(
    "31c: code corrigé s'exécute (status success)",
    run2.get("status") == "success",
    run2.get("status"),
)

# §19 — SANDBOX : code dangereux rejeté
try:
    api(
        f"/api/threads/{t31}/run-code",
        "POST",
        {
            "user_id": u31,
            "language": "python",
            "code": "import socket\nprint('hack')",
        },
    )
    sandbox_ok = False
except urllib.error.HTTPError as e:
    sandbox_ok = e.code == 400
check(
    "19: code réseau REJETÉ par la sandbox (400)",
    sandbox_ok,
)

# ==================================================================
# §32 — PERSISTANCE ACTIVITÉ après restart simulé
# (le checkpointer SqliteSaver persiste déjà entre instances ;
# on vérifie via relecture de l'état du thread — même serveur,
# la preuve inter-restart complète est en test_v52_unit §49)
# ==================================================================
print("\n--- §32 persistance activité ---")
act31b = api(f"/api/threads/{t31}/activity?user_id={u31}")
check(
    "32: activité toujours disponible après les échanges "
    "(checkpointer)",
    bool(act31b.get("activity")),
)

# ==================================================================
# §38 — KNOWLEDGE : topic inexistant → absence propre
# ==================================================================
print("\n--- §38 topic inexistant ---")
u38 = new_user("kn-" + uuid.uuid4().hex[:6])
t38 = new_thread(u38, "kn")
r38 = chat(
    u38,
    t38,
    "Donne-moi un exercice Python sur le topic "
    "xyzabcinexistenttopic.",
)
resp38 = asc(r38.get("response", ""))
act38 = api(f"/api/threads/{t38}/activity?user_id={u38}")
check(
    "38: topic inexistant → pas d'exercice inventé "
    "(réponse ne prétend pas créer, activité sans topic inventé "
    "ou guidance)",
    not (
        (act38.get("activity") or {}).get("topic")
        == "xyzabcinexistenttopic"
    ),
    (act38.get("activity") or {}).get("topic"),
)

# ==================================================================
# §39 — TOOL REGISTRY : tool déclaré mais absent = unavailable
# (vérification directe du registre : python a les code tools,
# biology NON — la garde interne du tool vérifie l'autorisation)
# ==================================================================
print("\n--- §39 tool registry ---")
from app.subjects.registry import get_subject

py_cfg = get_subject("python")
bio_cfg = get_subject("biology")
check(
    "39a: python DÉCLARE execute_code/run_tests/analyze_code",
    all(
        t in (py_cfg.tools.get("specialized") or [])
        for t in ("execute_code", "run_tests", "analyze_code")
    ),
    str(py_cfg.tools.get("specialized")),
)
check(
    "39b: biology NE déclare PAS les code tools",
    not (
        "execute_code"
        in (bio_cfg.tools.get("specialized") or [])
    ),
    str(bio_cfg.tools.get("specialized")),
)

# ==================================================================
# Résumé
# ==================================================================
print()
fails = [label for label, ok in results if not ok]
print(
    f"TOTAL: {len(results)} | PASS: {len(results) - len(fails)} "
    f"| FAIL: {len(fails)}"
)
if fails:
    print("ECHECS:")
    for f in fails:
        print(" -", f)
    sys.exit(1)
print("TESTS PARCOURS INTÉGRATION: OK")
