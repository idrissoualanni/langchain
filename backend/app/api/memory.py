# Routes Memory — state + historique des checkpoints
from fastapi import APIRouter, HTTPException

from app.agent.runner import (
    get_thread_history,
    get_thread_state,
)
from app.api.schemas import CheckpointOut, StateResponse
from app.db.connections import init_db
from app.db.threads import get_thread, thread_belongs_to_user

router = APIRouter(prefix="/api/threads", tags=["memory"])


def _validate_thread_access(
    thread_id: str, user_id: str | None
) -> dict:
    """Valide l'accès : thread existe + (si user fourni) appartient au user."""
    init_db()
    thread = get_thread(thread_id)
    if thread is None:
        raise HTTPException(
            status_code=404, detail="Thread introuvable"
        )

    if user_id is not None and not thread_belongs_to_user(
        thread_id, user_id
    ):
        raise HTTPException(
            status_code=403,
            detail="Ce thread n'appartient pas à cet utilisateur",
        )
    return thread


@router.get("/{thread_id}/state", response_model=StateResponse)
def api_thread_state(
    thread_id: str, user_id: str | None = None
) -> StateResponse:
    """State courant : user_id, interactions, messages, dernier checkpoint."""
    _validate_thread_access(thread_id, user_id)
    state = get_thread_state(user_id or "", thread_id)
    if state is None:
        # Thread sans historique LangGraph (créé mais jamais utilisé)
        return StateResponse(
            user_id=user_id or "",
            thread_id=thread_id,
            interaction_count=0,
            message_count=0,
            messages=[],
        )
    return StateResponse(**state)


@router.get(
    "/{thread_id}/history", response_model=list[CheckpointOut]
)
def api_thread_history(
    thread_id: str, user_id: str | None = None
) -> list[CheckpointOut]:
    """Historique des checkpoints (timeline)."""
    _validate_thread_access(thread_id, user_id)
    history = get_thread_history(user_id or "", thread_id)
    return [CheckpointOut(**h) for h in history]
