# Routes Activity V5.2 — état d'activité pédagogique du thread +
# exécution directe de code (Code Editor frontend, §24-§26).
#
# Sécurité (§51 cross-user) : chaque endpoint valide que le thread
# appartient à l'utilisateur AVANT toute lecture du state.
#
# Mission Identité : ownership dérivé de la SESSION — le user_id
# ( query / body ) est vérifié contre l'utilisateur courant , pas
# cru sur parole ( 403 si usurpation ).
from fastapi import APIRouter, Depends, HTTPException

from app.schemas.activity import summarize_activity
from app.agent.code_tools import (
    MAX_CODE_CHARS,
    run_python_isolated,
    static_security_scan,
)
from app.agent.runner import get_thread_state
from app.schemas import (
    CodeRunRequest,
    CodeRunResponse,
    ThreadActivityResponse,
)
from app.auth.resolver import CurrentUser, get_current_user
from app.db.connections import init_db
from app.db.threads import get_thread, thread_belongs_to_user
from app.logging.events import log_event

router = APIRouter(prefix="/api/threads", tags=["activity"])


def _validate_thread_access(
    thread_id: str, user_id: str, current: CurrentUser
) -> dict:
    """Valide l'accès : thread existe ET appartient au user (§51).

    Mission Identité : user_id doit correspondre à la session ( le
    paramètre reste pour rétrocompatibilité mais ne peut JAMAIS
    désigner autrui ).
    """
    init_db()
    thread = get_thread(thread_id)
    if thread is None:
        raise HTTPException(
            status_code=404, detail="Thread introuvable"
        )
    if not current.is_admin:
        if not thread_belongs_to_user(thread_id, current.user_id):
            raise HTTPException(
                status_code=403,
                detail="Ce thread n'appartient pas à cet utilisateur",
            )
        if user_id != current.user_id:
            raise HTTPException(
                status_code=403,
                detail="user_id ne correspond pas à la session",
            )
    return thread


@router.get(
    "/{thread_id}/activity",
    response_model=ThreadActivityResponse,
)
def api_thread_activity(
    thread_id: str,
    user_id: str,
    current: CurrentUser = Depends(get_current_user),
) -> ThreadActivityResponse:
    """État de l'activité pédagogique en cours dans CE thread.

    Thread-local (§50) : l'activité du thread A n'est jamais
    visible depuis le thread B. Le user_id est REQUIS et doit
    correspondre à la session (§51).
    """
    _validate_thread_access(thread_id, user_id, current)

    state = get_thread_state(user_id, thread_id) or {}

    # Le state runner n'expose pas learning_activity directement —
    # on le lit depuis le snapshot complet
    from app.graph.main import get_agent

    snapshot = get_agent().get_state(
        {
            "configurable": {
                "thread_id": thread_id,
                "user_id": user_id,
            }
        }
    )
    values = snapshot.values if snapshot else {}
    activity = values.get("learning_activity") or {}
    activity_log = values.get("activity_log") or []

    summary = summarize_activity(activity)

    return ThreadActivityResponse(
        thread_id=thread_id,
        user_id=user_id,
        activity=summary,
        activity_log=activity_log[-50:],
        interaction_count=state.get("interaction_count", 0),
    )


@router.post(
    "/{thread_id}/run-code",
    response_model=CodeRunResponse,
)
def api_run_code(
    thread_id: str,
    payload: CodeRunRequest,
    current: CurrentUser = Depends(get_current_user),
) -> CodeRunResponse:
    """Exécute le code du Code Editor dans la sandbox isolée.

    Backend tool (§24) : le frontend permet d'ÉCRIRE le code ; cette
    route l'EXÉCUTE côté backend dans le sous-processus isolé
    (env purgé, réseau/fichiers bloqués, timeout dur). Les
    événements CODE_EXECUTION_* émis sont réels (§33).
    """
    _validate_thread_access(thread_id, payload.user_id, current)

    if not payload.code or not payload.code.strip():
        raise HTTPException(
            status_code=400, detail="Code vide"
        )
    if len(payload.code) > MAX_CODE_CHARS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Code trop long (max {MAX_CODE_CHARS} caractères)"
            ),
        )

    violations = static_security_scan(payload.code)
    if violations:
        log_event(
            "CODE_EXECUTION_ERROR",
            level="WARNING",
            message=(
                f"API run-code rejected | violations={len(violations)}"
            ),
            user_id=payload.user_id,
            thread_id=thread_id,
        )
        raise HTTPException(
            status_code=400,
            detail=(
                "Code rejeté par la sécurité : accès fichiers/réseau/"
                "processus/eval interdit pour le code étudiant."
            ),
        )

    log_event(
        "CODE_EXECUTION_START",
        message=(
            f"API run-code | chars={len(payload.code)}"
        ),
        user_id=payload.user_id,
        thread_id=thread_id,
    )

    result = run_python_isolated(payload.code)

    log_event(
        "CODE_EXECUTION_END"
        if result["status"] == "success"
        else "CODE_EXECUTION_ERROR",
        message=(
            f"API run-code done | status={result['status']} | "
            f"exit={result['exit_code']}"
        ),
        user_id=payload.user_id,
        thread_id=thread_id,
        extra={
            "status": result["status"],
            "exit_code": result["exit_code"],
            "duration_ms": result["duration_ms"],
        },
    )

    return CodeRunResponse(
        status=result["status"],
        stdout=result["stdout"],
        stderr=result["stderr"],
        exit_code=result["exit_code"],
        duration_ms=result["duration_ms"],
    )
