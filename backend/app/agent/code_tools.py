from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Annotated

from langchain.tools import InjectedState, InjectedToolCallId
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.config import RunnableConfig
from langgraph.types import Command

from app.logging.events import log_event

# ------------------------------------------------------------------
# Garde de disponibilité (§37) — le subject config autorise-t-il ?
# ------------------------------------------------------------------


def _code_tools_enabled(subject: str | None) -> bool:
    """Les tools de code sont-ils autorisés pour ce subject ?

    Générique (§38) : la SubjectConfig déclare execute_code dans
    tools.specialized → autorisé. Aucun if subject == 'python'.
    """
    if not subject:
        return False
    from app.subjects.registry import get_subject

    cfg = get_subject(subject)
    if cfg is None:
        return False
    specialized = cfg.tools.get("specialized", []) or []
    common = cfg.tools.get("common", []) or []
    return "execute_code" in specialized or "execute_code" in common


def _disabled_message(tool_name: str, subject: str | None) -> str:
    return (
        f"Le tool {tool_name} n'est pas disponible pour la matière "
        f"'{subject or '?'}' : la configuration du sujet n'autorise "
        "pas l'exécution de code ici. Explique à l'étudiant que cet "
        "exercice se pratique en explication, pas en exécution."
    )


# ------------------------------------------------------------------
# Analyse statique de sécurité (pré-exécution)
# ------------------------------------------------------------------

# Imports/mots-clés réseau et système interdits au code étudiant
_BLOCKED_IMPORTS = {
    "socket",
    "sockets",
    "ssl",
    "requests",
    "urllib",
    "urllib2",
    "urllib3",
    "http",
    "httpx",
    "aiohttp",
    "ftplib",
    "smtplib",
    "telnetlib",
    "subprocess",
    "multiprocessing",
    "threading",
    "ctypes",
    "os",
    "sys",
    "pathlib",
    "shutil",
    "signal",
    "resource",
    "pickle",
    "shelve",
    "ctypes.util",
}

_BLOCKED_PATTERNS = [
    r"\bimport\s+os\b",
    r"\bfrom\s+os\b",
    r"\bimport\s+sys\b",
    r"\bfrom\s+sys\b",
    r"\bimport\s+socket\b",
    r"\bfrom\s+socket\b",
    r"\bimport\s+subprocess\b",
    r"\bfrom\s+subprocess\b",
    r"\bimport\s+requests\b",
    r"\bfrom\s+requests\b",
    r"\bimport\s+urllib\b",
    r"\bfrom\s+urllib\b",
    r"\bimport\s+http\b",
    r"\bfrom\s+http\b",
    r"\bimport\s+ctypes\b",
    r"\bfrom\s+ctypes\b",
    r"\bimport\s+shutil\b",
    r"\bfrom\s+shutil\b",
    r"\bimport\s+pathlib\b",
    r"\bfrom\s+pathlib\b",
    r"\b__import__\s*\(",
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"\bcompile\s*\(",
    r"\bglobals\s*\(\s*\)",
    r"\blocals\s*\(\s*\)",
    r"\bopen\s*\(",
]


def static_security_scan(code: str) -> list[str]:
    """Analyse statique du code AVANT exécution : détecte les
    patterns interdits (réseau, système, fichier, introspection).
    Retourne la liste des violations détectées."""
    violations: list[str] = []
    for pattern in _BLOCKED_PATTERNS:
        if re.search(pattern, code):
            violations.append(pattern)
    return violations


# ------------------------------------------------------------------
# Exécution sandboxée locale (processus séparé)
# ------------------------------------------------------------------

# Limites par exécution
EXEC_TIMEOUT_S = 10          # secondes max d'exécution
MAX_CODE_CHARS = 8_000       # taille max du code soumis
MAX_OUTPUT_CHARS = 8_000     # stdout+stderr bornés
MAX_RUNS_PER_THREAD = 40     # anti-abus par thread


def _sandbox_root() -> Path:
    """Racine des répertoires d'exécution jetables.

    Sous le répertoire database du projet (sweep au démarrage) :
    - reste dans le périmètre du backend (pas de TMP système) ;
    - un répertoire par run, supprimé après exécution.
    """
    from app.config import DATABASE_DIR

    root = DATABASE_DIR / "code_runs"
    root.mkdir(exist_ok=True)
    return root


def _safe_env() -> dict:
    """Environnement minimal du sous-processus — SECRETS SUPPRIMÉS.

    Le code étudiant ne doit voir ni OLLAMA_API_KEY, ni .env du
    serveur, ni quoi que ce soit du processus principal. On ne
    garde que le strict minimum pour l'interpréteur.
    """
    return {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "HOME": str(_sandbox_root()),
        "TMPDIR": str(_sandbox_root()),
        "LANG": "C.UTF-8",
    }


def run_python_isolated(
    code: str,
    timeout_s: int = EXEC_TIMEOUT_S,
) -> dict:
    """Exécute le code Python dans un sous-processus isolé.

    Isolation :
      - python -I (mode isolé : sys.path réduit, pas de site de
        l'utilisateur) ;
      - env purgé (_safe_env) ;
      - cwd = répertoire jetable dédié sous backend/database ;
      - timeout dur (kill du processus à l'expiration).

    Retour : {status, stdout, stderr, exit_code, duration_ms}
    """
    import shutil
    import uuid as _uuid

    started = time.perf_counter()

    tmp = _sandbox_root() / f"run-{_uuid.uuid4().hex[:12]}"
    tmp.mkdir(exist_ok=True)
    try:
        script = tmp / "student_code.py"
        script.write_text(code, encoding="utf-8")

        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    str(script),
                ],
                capture_output=True,
                text=True,
                timeout=timeout_s,
                cwd=str(tmp),
                env=_safe_env(),
            )
            stdout = (proc.stdout or "")[:MAX_OUTPUT_CHARS]
            stderr = (proc.stderr or "")[:MAX_OUTPUT_CHARS]
            exit_code = proc.returncode
            status = "success" if exit_code == 0 else "error"
        except subprocess.TimeoutExpired as exc:
            stdout = ((exc.stdout or b"").decode(
                "utf-8", errors="replace"
            ) if isinstance(exc.stdout, bytes) else (exc.stdout or ""))[
                :MAX_OUTPUT_CHARS
            ]
            stderr = (
                "Timeout : exécution interrompue après "
                f"{timeout_s}s (limite de sécurité)."
            )
            exit_code = -1
            status = "timeout"
        except Exception as exc:  # pragma: no cover — défense
            stdout = ""
            stderr = f"Erreur d'exécution : {exc}"
            exit_code = -1
            status = "error"
    finally:
        # Nettoyage silencieux du répertoire jetable
        shutil.rmtree(tmp, ignore_errors=True)

    duration_ms = int((time.perf_counter() - started) * 1000)
    return {
        "status": status,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
    }


# ------------------------------------------------------------------
# EXECUTE_CODE (§24-§27)
# ------------------------------------------------------------------


@tool
def execute_code(
    language: str,
    code: str,
    subject: str = "",
    state: Annotated[dict | None, InjectedState] = None,
    tool_call_id: Annotated[str | None, InjectedToolCallId] = None,
    config: RunnableConfig = None,
) -> Command:
    """Exécute le code de l'étudiant dans un environnement isolé et
    retourne le résultat réel (stdout, stderr, exit_code).

    UTILISATION : après que l'étudiant a écrit du code dans l'éditeur
    (exercice expected_response_type=code), pour qu'il voie le
    résultat de SON code. Le feedback pédagogique reste ton rôle :
    ne réécris JAMAIS son code corrigé sans permission (§31) —
    identifie, explique, questionne, laisse corriger.

    SÉCURITÉ : le code tourne dans un sous-processus isolé (env
    purgé, réseau/fichiers/processus bloqués, timeout 10s). Le code
    réseau/système/fichier est rejeté avant exécution.

    Args:
        language: langage du code — seul "python" est supporté.
        code: le code complet de l'étudiant, mot pour mot.
        subject: id de la matière (ex: "python") — requis pour
            vérifier que la matière autorise l'exécution de code.
    """
    user_id, thread_id = _thread_ids(config)
    tool_name = "execute_code"

    log_event(
        "TOOL_CALL",
        message=(
            f"execute_code language={language} "
            f"chars={len(code or '')} subject={subject}"
        ),
        tool_name=tool_name,
        user_id=user_id,
        thread_id=thread_id,
    )

    # ---- Garde : disponibilité (§37) ----
    if not _code_tools_enabled(subject):
        log_event(
            "CODE_EXECUTION_ERROR",
            level="WARNING",
            message=(
                f"execute_code disabled for subject '{subject}' "
                "(not declared in tools.specialized)"
            ),
            tool_name=tool_name,
            user_id=user_id,
            thread_id=thread_id,
        )
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=_disabled_message(
                            tool_name, subject
                        ),
                        tool_call_id=tool_call_id or "",
                    )
                ]
            }
        )

    # ---- Garde : langage ----
    if (language or "").lower() not in ("python", "py", "python3"):
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            f"Langage '{language}' non supporté : "
                            "seul python est exécutable pour le "
                            "moment."
                        ),
                        tool_call_id=tool_call_id or "",
                    )
                ]
            }
        )

    # ---- Garde : taille ----
    if not code or not code.strip():
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            "Aucun code fourni. Demande à l'étudiant "
                            "d'écrire son code dans l'éditeur."
                        ),
                        tool_call_id=tool_call_id or "",
                    )
                ]
            }
        )
    if len(code) > MAX_CODE_CHARS:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            f"Code trop long ({len(code)} > "
                            f"{MAX_CODE_CHARS} caractères). "
                            "Demande une version plus courte."
                        ),
                        tool_call_id=tool_call_id or "",
                    )
                ]
            }
        )

    # ---- Anti-abus : quota de runs par thread ----
    runs = _thread_code_runs(state)
    if runs >= MAX_RUNS_PER_THREAD:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            "Quota d'exécutions atteint pour ce "
                            "thread. Poursuivez l'analyse sans "
                            "exécution."
                        ),
                        tool_call_id=tool_call_id or "",
                    )
                ]
            }
        )

    # ---- Analyse statique de sécurité (§27) ----
    violations = static_security_scan(code)
    if violations:
        log_event(
            "CODE_EXECUTION_ERROR",
            level="WARNING",
            message=(
                f"Code rejected by static security scan | "
                f"violations={len(violations)}"
            ),
            tool_name=tool_name,
            user_id=user_id,
            thread_id=thread_id,
            extra={"violations": violations[:10]},
        )
        return Command(
            update={
                "activity_log": [
                    _log_entry(
                        "CODE_EXECUTION_ERROR",
                        "rejected",
                        f"static scan: {len(violations)} violation(s)",
                        tool_name,
                    )
                ],
                "messages": [
                    ToolMessage(
                        content=(
                            "CODE REJETÉ PAR LA SÉCURITÉ — pour "
                            "l'entraînement, le code ne peut pas : "
                            "accéder aux fichiers (open), au réseau "
                            "(socket/requests/urllib), aux processus "
                            "(subprocess/os/sys), ni utiliser "
                            "eval/exec/__import__. Réécris l'exercice "
                            "sans ces éléments et explique à "
                            "l'étudiant pourquoi."
                        ),
                        tool_call_id=tool_call_id or "",
                    )
                ],
            }
        )

    # ---- Exécution réelle ----
    log_event(
        "CODE_EXECUTION_START",
        message=(
            f"Executing student code | lang={language} | "
            f"chars={len(code)}"
        ),
        tool_name=tool_name,
        user_id=user_id,
        thread_id=thread_id,
    )

    result = run_python_isolated(code)

    log_event(
        "CODE_EXECUTION_END",
        message=(
            f"Code executed | status={result['status']} | "
            f"exit={result['exit_code']} | "
            f"{result['duration_ms']}ms"
        ),
        tool_name=tool_name,
        user_id=user_id,
        thread_id=thread_id,
        extra={
            "status": result["status"],
            "exit_code": result["exit_code"],
            "duration_ms": result["duration_ms"],
        },
    )
    if result["status"] in ("error", "timeout"):
        log_event(
            "CODE_EXECUTION_ERROR",
            level="WARNING",
            message=(
                f"Code execution {result['status']} | "
                f"{result['stderr'][:200]}"
            ),
            tool_name=tool_name,
            user_id=user_id,
            thread_id=thread_id,
        )

    # ---- Feedback structuré pour le LLM ----
    if result["status"] == "success":
        content = (
            "EXÉCUTION RÉUSSIE\n\n"
            f"stdout :\n{result['stdout'] or '(vide)'}\n\n"
            f"exit_code : 0 | durée : {result['duration_ms']}ms\n\n"
            "PÉDAGOGIE : fais le lien entre ce que l'étudiant "
            "voulait et ce que le code produit. Si le résultat "
            "répond à la consigne → félicite puis vérifie la "
            "compréhension (assess_understanding). Sinon → "
            "identifie le problème, questionne, laisse l'étudiant "
            "corriger (§31)."
        )
    elif result["status"] == "timeout":
        content = (
            "EXÉCUTION INTERROMPUE (timeout sécurité)\n\n"
            f"stderr : {result['stderr']}\n\n"
            "PÉDAGOGIE : demande à l'étudiant s'il y a une boucle "
            "infinie et guide-le vers la condition d'arrêt."
        )
    else:
        content = (
            "ERREUR D'EXÉCUTION\n\n"
            f"stderr :\n{result['stderr']}\n\n"
            f"exit_code : {result['exit_code']}\n\n"
            "PÉDAGOGIE : ne donne PAS la correction complète. "
            "Identifie la ligne/type d'erreur, demande à l'étudiant "
            "ce qu'il en comprend, oriente avec une question. Il "
            "peut réessayer plusieurs fois (run again)."
        )

    return Command(
        update={
            "code_runs": runs + 1,
            "activity_log": [
                _log_entry(
                    "CODE_EXECUTION_START",
                    "started",
                    f"lang={language} chars={len(code)}",
                    tool_name,
                ),
                _log_entry(
                    "CODE_EXECUTION_END"
                    if result["status"] == "success"
                    else "CODE_EXECUTION_ERROR",
                    result["status"],
                    f"exit={result['exit_code']} "
                    f"{result['duration_ms']}ms",
                    tool_name,
                ),
            ],
            "messages": [
                ToolMessage(
                    content=content, tool_call_id=tool_call_id or ""
                )
            ],
        }
    )


def _thread_code_runs(state: dict | None) -> int:
    """Compteur de runs de code du thread (anti-abus)."""
    return int((state or {}).get("code_runs", 0) or 0)


def _log_entry(
    event: str, status: str, detail: str, tool_name: str
) -> dict:
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "event": event,
        "status": status,
        "detail": detail[:300],
        "hint_level": 0,
        "activity_type": "code_practice",
    }


def _thread_ids(config: RunnableConfig | None) -> tuple[str, str]:
    conf = (config or {}).get("configurable", {}) or {}
    return (
        conf.get("user_id", "") or "",
        conf.get("thread_id", "") or "",
    )


# ------------------------------------------------------------------
# RUN_TESTS (§28)
# ------------------------------------------------------------------


@tool
def run_tests(
    language: str,
    code: str,
    tests: list[dict],
    subject: str = "",
    state: Annotated[dict | None, InjectedState] = None,
    tool_call_id: Annotated[str | None, InjectedToolCallId] = None,
    config: RunnableConfig = None,
) -> Command:
    """Exécute des tests pédagogiques contre le code de l'étudiant et
    retourne les résultats réels (passed/failed par test).

    UTILISATION : pour un exercice de code avec critères vérifiables
    (ex: « la fonction somme retourne a+b »). Construis les tests
    DEPUIS LA CONSIGNE de l'exercice. Chaque test :
      {"name": "2 + 3", "call": "somme(2, 3)", "expected": "5"}
    - name   : libellé lisible du test ;
    - call   : expression Python appelant le code étudiant ;
    - expected : résultat attendu (repr comparé).

    Après les tests, explique les échecs pédagogiquement (§31) :
    n'écris pas la solution à sa place.

    Args:
        language: "python" uniquement.
        code: le code complet de l'étudiant (doit définir la/des
            fonction(s) testée(s)).
        tests: la liste des tests pédagogiques (max 10).
        subject: id de la matière — requis pour l'autorisation.
    """
    user_id, thread_id = _thread_ids(config)
    tool_name = "run_tests"

    log_event(
        "TOOL_CALL",
        message=(
            f"run_tests lang={language} tests={len(tests or [])} "
            f"subject={subject}"
        ),
        tool_name=tool_name,
        user_id=user_id,
        thread_id=thread_id,
    )

    if not _code_tools_enabled(subject):
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=_disabled_message(tool_name, subject),
                        tool_call_id=tool_call_id or "",
                    )
                ]
            }
        )

    if (language or "").lower() not in ("python", "py", "python3"):
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            f"Langage '{language}' non supporté "
                            "(python uniquement)."
                        ),
                        tool_call_id=tool_call_id or "",
                    )
                ]
            }
        )

    if not code or not code.strip():
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            "Aucun code à tester. Demande le code à "
                            "l'étudiant."
                        ),
                        tool_call_id=tool_call_id or "",
                    )
                ]
            }
        )

    tests = (tests or [])[:10]
    if not tests:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            "Aucun test fourni. Construis les tests "
                            "depuis la consigne de l'exercice."
                        ),
                        tool_call_id=tool_call_id or "",
                    )
                ]
            }
        )

    # Sécurité : le code étudiant est scanné, et les appels de test
    # sont des expressions simples (pas de statements).
    violations = static_security_scan(code)
    for t in tests:
        call = str(t.get("call", ""))
        if ";" in call or "\n" in call:
            violations.append("multi-statement test call")

    if violations:
        log_event(
            "CODE_TEST_ERROR",
            level="WARNING",
            message=f"Tests rejected | violations={len(violations)}",
            tool_name=tool_name,
            user_id=user_id,
            thread_id=thread_id,
        )
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            "TESTS REJETÉS PAR LA SÉCURITÉ : le code "
                            "utilise des éléments interdits "
                            "(fichiers/réseau/processus/eval). "
                            "Reformule l'exercice."
                        ),
                        tool_call_id=tool_call_id or "",
                    )
                ]
            }
        )

    # ---- Génération du script de test isolé ----
    # Chaque test devient : try: actual = repr(eval(call)) except...
    # exécuté dans le MÊME sous-processus isolé qu'execute_code.
    lines = [code, "", "results = []"]
    for t in tests:
        name = str(t.get("name", "test"))[:100]
        call = str(t.get("call", ""))
        expected = t.get("expected", "")
        # Comparaison NORMALISÉE (fix bug #1 mission intégration) :
        # _actual = repr(call) renvoie une CHAÎNE (ex: '5') ;
        # repr(expected) renvoie '"5"' quand le LLM passe la
        # chaîne "5" pour un résultat numérique → comparaison
        # str vs str-quotée systématiquement fausse (0/3).
        # Fix : les deux côtés en chaîne — _actual == repr
        # (expected) OU _actual == str(expected). 2 passent,
        # 1 échoue sur le test réel (48d).
        expected_repr = repr(expected)
        lines.append("try:")
        lines.append(f"    _actual = repr({call})")
        lines.append("    results.append({")
        lines.append(f"        'name': {name!r},")
        lines.append("        'actual': _actual,")
        lines.append(f"        'expected': {expected_repr},")
        lines.append(
            "        'passed': _actual == "
            f"{expected_repr} or _actual == {str(expected)!r},"
        )
        lines.append("    })")
        lines.append("except Exception as _e:")
        lines.append("    results.append({")
        lines.append(f"        'name': {name!r},")
        lines.append("        'actual': f'erreur: {_e}',")
        lines.append(f"        'expected': {expected_repr},")
        lines.append("        'passed': False,")
        lines.append("    })")
    lines.append(
        "import json; print(json.dumps(results))"
    )

    harness = "\n".join(lines)

    log_event(
        "CODE_TEST_START",
        message=f"Running {len(tests)} tests",
        tool_name=tool_name,
        user_id=user_id,
        thread_id=thread_id,
    )

    result = run_python_isolated(harness, timeout_s=15)

    # ---- Parse les résultats ----
    import json as _json

    parsed: list[dict] = []
    out = result["stdout"].strip()
    if result["status"] == "success" and out:
        try:
            # Le dernier bloc JSON de stdout = résultats
            start = out.find("[")
            end = out.rfind("]")
            if start != -1 and end != -1:
                parsed = _json.loads(out[start : end + 1])
        except Exception:
            parsed = []

    if not parsed and result["status"] != "success":
        log_event(
            "CODE_TEST_ERROR",
            level="WARNING",
            message=f"Test harness failed | {result['stderr'][:200]}",
            tool_name=tool_name,
            user_id=user_id,
            thread_id=thread_id,
        )
        return Command(
            update={
                "activity_log": [
                    _log_entry(
                        "CODE_TEST_ERROR",
                        "error",
                        result["stderr"][:200],
                        tool_name,
                    )
                ],
                "messages": [
                    ToolMessage(
                        content=(
                            "IMPOSSIBLE D'EXÉCUTER LES TESTS — le "
                            f"code ne se compile pas :\n\n"
                            f"{result['stderr'][:1000]}\n\n"
                            "PÉDAGOGIE : identifie l'erreur de "
                            "syntaxe, oriente l'étudiant, laisse-le "
                            "corriger."
                        ),
                        tool_call_id=tool_call_id or "",
                    )
                ],
            }
        )

    passed = sum(1 for t in parsed if t.get("passed"))
    failed = len(parsed) - passed

    log_event(
        "CODE_TEST_END",
        message=(
            f"Tests done | passed={passed} | failed={failed}"
        ),
        tool_name=tool_name,
        user_id=user_id,
        thread_id=thread_id,
        extra={"passed": passed, "failed": failed},
    )

    test_lines = [
        f"{'✓' if t.get('passed') else '✗'} {t.get('name')} "
        f"— obtenu : {t.get('actual')} / attendu : "
        f"{t.get('expected')}"
        for t in parsed
    ]

    content = (
        f"RÉSULTATS DES TESTS — {passed}/{len(parsed)} réussis\n\n"
        + "\n".join(test_lines)
        + "\n\nPÉDAGOGIE (§31) : pour chaque test raté, identifie "
        "l'écart, questionne l'étudiant, propose un indice — ne "
        "réécris pas son code. Il peut corriger et relancer."
    )

    return Command(
        update={
            "activity_log": [
                _log_entry(
                    "CODE_TEST_START",
                    "started",
                    f"{len(tests)} tests",
                    tool_name,
                ),
                _log_entry(
                    "CODE_TEST_END",
                    "done",
                    f"passed={passed} failed={failed}",
                    tool_name,
                ),
            ],
            "messages": [
                ToolMessage(
                    content=content, tool_call_id=tool_call_id or ""
                )
            ],
        }
    )


# ------------------------------------------------------------------
# ANALYZE_CODE (§29-§30)
# ------------------------------------------------------------------

# Observations de style/logique détectables statiquement en Python
_PY_STYLE_RULES = [
    (
        r"print\s*\(",
        "style",
        "low",
        "La fonction utilise print — pour un exercice qui demande "
        "une valeur RETOURNÉE, print affiche sans renvoyer (§31 : "
        "vérifie la consigne).",
    ),
    (
        r"def\s+\w+\s*\([^)]*\)\s*:\s*(\n\s*)*return\b",
        "logic",
        "info",
        "La fonction retourne une valeur — cohérent si la consigne "
        "demande un retour.",
    ),
    (
        r"except\s*:\s*$",
        "style",
        "medium",
        "except nu (sans type d'exception) masque les erreurs — "
        "préciser le type d'exception attendu.",
    ),
    (
        r"while\s+True\s*:",
        "logic",
        "medium",
        "Boucle while True sans condition d'arrêt visible — risque "
        "de boucle infinie.",
    ),
    (
        r"=\s*\[\s*\]\s*\)",
        "logic",
        "medium",
        "Valeur par défaut mutable (liste vide) — piège classique, "
        "préférer None.",
    ),
    (
        r"^\s*class\s+\w+\((.*?)\)\s*:\s*$",
        "style",
        "low",
        "Définition de classe détectée — vérifier la cohérence avec "
        "la consigne.",
    ),
]


@tool
def analyze_code(
    language: str,
    code: str,
    subject: str = "",
    state: Annotated[dict | None, InjectedState] = None,
    tool_call_id: Annotated[str | None, InjectedToolCallId] = None,
    config: RunnableConfig = None,
) -> Command:
    """Analyse le code de l'étudiant SANS l'exécuter : syntaxe,
    bugs évidents, style et observations logiques — observations
    structurées, PAS une deuxième personnalité pédagogique (§29).

    UTILISATION : en complément d'execute_code/run_tests pour guider
    la révision AVANT/après exécution. Tu restes LE tuteur : ce tool
    fournit des observations, tu choisis comment les exploiter.

    Args:
        language: langage ("python").
        code: le code complet de l'étudiant.
        subject: id de la matière — pour l'autorisation.
    """
    user_id, thread_id = _thread_ids(config)
    tool_name = "analyze_code"

    log_event(
        "TOOL_CALL",
        message=(
            f"analyze_code lang={language} chars={len(code or '')} "
            f"subject={subject}"
        ),
        tool_name=tool_name,
        user_id=user_id,
        thread_id=thread_id,
    )

    if not _code_tools_enabled(subject):
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=_disabled_message(tool_name, subject),
                        tool_call_id=tool_call_id or "",
                    )
                ]
            }
        )

    if not code or not code.strip():
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            "Aucun code à analyser. Demande le code "
                            "à l'étudiant."
                        ),
                        tool_call_id=tool_call_id or "",
                    )
                ]
            }
        )

    issues: list[dict] = []

    # ---- Syntaxe : compile() SANS exécuter (défense : try/except) ----
    syntax_error = None
    try:
        compile(code, "<student_code>", "exec")
    except SyntaxError as exc:
        syntax_error = (
            f"Ligne {exc.lineno} : {exc.msg}"
            + (f" — « {exc.text.strip()} »" if exc.text else "")
        )
        issues.append(
            {
                "type": "syntax",
                "severity": "high",
                "message": syntax_error,
            }
        )

    # ---- Règles statiques de style/logique ----
    for pattern, issue_type, severity, message in _PY_STYLE_RULES:
        if syntax_error:
            break  # inutile d'empiler si ça ne compile pas
        if re.search(pattern, code, re.MULTILINE):
            issues.append(
                {
                    "type": issue_type,
                    "severity": severity,
                    "message": message,
                }
            )

    # ---- Indentation/structure basique ----
    if not syntax_error:
        if "\t" in code:
            issues.append(
                {
                    "type": "style",
                    "severity": "low",
                    "message": (
                        "Tabulations détectées — PEP 8 recommande "
                        "4 espaces."
                    ),
                }
            )
        lines = [ln for ln in code.splitlines() if ln.strip()]
        if len(lines) > 50:
            issues.append(
                {
                    "type": "style",
                    "severity": "low",
                    "message": (
                        "Code long — vérifier s'il peut être "
                        "simplifié/découpé."
                    ),
                }
            )

    content_lines: list[str] = []
    if not issues:
        content_lines.append(
            "Aucun problème détecté. Le code compile et suit les "
            "règles de style de base."
        )
    else:
        for issue in issues:
            icon = {
                "high": "✗",
                "medium": "⚠",
                "low": "·",
                "info": "ℹ",
            }.get(issue["severity"], "·")
            content_lines.append(
                f"{icon} [{issue['type']}|{issue['severity']}] "
                f"{issue['message']}"
            )

    content = (
        f"ANALYSE DE CODE — {language}\n\n"
        + "\n".join(content_lines)
        + "\n\nPÉDAGOGIE (§29/§31) : ces observations sont brutes. "
        "Choisis LES PLUS PÉDAGOGIQUES, questionne l'étudiant "
        "(« vois-tu pourquoi ? »), ne corrige pas à sa place."
    )

    log_event(
        "CODE_ANALYSIS",
        message=(
            f"Code analyzed | issues={len(issues)} | "
            f"syntax_error={bool(syntax_error)}"
        ),
        tool_name=tool_name,
        user_id=user_id,
        thread_id=thread_id,
        extra={"issues_count": len(issues)},
    )

    return Command(
        update={
            "activity_log": [
                _log_entry(
                    "CODE_ANALYSIS",
                    "done",
                    f"{len(issues)} issue(s)",
                    tool_name,
                )
            ],
            "messages": [
                ToolMessage(
                    content=content, tool_call_id=tool_call_id or ""
                )
            ],
        }
    )


code_tools = [execute_code, run_tests, analyze_code]
