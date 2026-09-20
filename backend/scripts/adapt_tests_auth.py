# Mission Identité — adaptation des suites de régression au
# Bearer token ( mode dev : "dev:<internal_user_id>" ).
#
# Pattern : chaque suite HTTP a un helper api() + new_user().
# Adaptation :
#   - new_user() : POST /api/users ( dev only ) → capture dev_token
#     et le STOKE dans un dict global TOKENS[user_id]
#   - api() : injecte Authorization: Bearer dev:<uid> automatiquement
#     selon le user_id présent dans l'URL/body quand connu ;
#     sinon prend le dernier token actif.
#
# Les fichiers sont patchés de façon MINIMALE ( helper seulement ,
# les assertions métier restent inchangées ).
import re
import sys
from pathlib import Path

API_HELPER = '''
TOKENS = {{}}  # user_id -> dev token ( session simulée mode dev )
LAST_TOKEN = [None]


def api(path, method="GET", body=None, token=None):
    import json as _json
    import urllib.request as _rq
    data = _json.dumps(body).encode() if body is not None else None
    headers = {{"Content-Type": "application/json"}}
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
'''


def patch(path: Path, new_user_body: str) -> bool:
    src = path.read_text(encoding="utf-8")
    if "TOKENS = {}" in src:
        print(f"[SKIP] déjà adapté : {path.name}")
        return True
    # 1. remplacer le helper api() existant
    m = re.search(
        r'def api\(path, method="GET", body=None\):.*?return json\.loads\(resp\.read\(\)\.decode\(\)\)',
        src,
        re.S,
    )
    if not m:
        print(f"[WARN] helper api() non trouvé : {path.name}")
        return False
    src = src.replace(m.group(0), API_HELPER.strip().format())
    # import re si absent
    if not re.search(r"^import re$", src, re.M):
        src = src.replace("import sys", "import re\nimport sys", 1)
    # 2. new_user capture le dev_token
    old = re.search(
        r'def new_user\(name\):\n    return api\("/api/users", "POST", \{"name": name\}\)\["user_id"\]',
        src,
    )
    if old:
        src = src.replace(
            old.group(0),
            'def new_user(name):\n'
            '    u = api("/api/users", "POST", {"name": name})\n'
            '    TOKENS[u["user_id"]] = u.get("dev_token", "dev:" + u["user_id"])\n'
            '    LAST_TOKEN[0] = TOKENS[u["user_id"]]\n'
            '    return u["user_id"]',
        )
    path.write_text(src, encoding="utf-8")
    print(f"[OK] patché : {path.name}")
    return True


def main() -> int:
    tests = Path("tests")
    ok = True
    for name in [
        "test_v5_integration.py",
        "test_v6_integration.py",
        "test_final_integration.py",
        "test_v65_search.py",
        "test_v7_learning_engine.py",
        "test_v52_unit.py",
    ]:
        p = tests / name
        if not p.exists():
            print(f"[MISS] {name}")
            continue
        ok = patch(p, "") and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
