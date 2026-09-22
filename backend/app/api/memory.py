# Routes Memory — state + historique des checkpoints
#
# Mission Identité : le BYPASS identifié par l'audit est FERMÉ.
# Avant : user_id OPTIONNEL en query — absence de user_id =
# lecture du state/history de n'importe quel thread. Désormais
# l'ownership est dérivé de la SESSION ( get_current_user ) et le
# user_id query, s'il est fourni, doit correspondre ( 403 sinon ).
from fastapi import APIRouter, Depends, HTTPException

from app.services.agent.runner import (
    get_thread_history,
    get_thread_state,
)
from app.schemas import CheckpointOut, StateResponse
from app.auth.resolver import CurrentUser, get_current_user
from app.infrastructure.database.connections import init_db
from app.infrastructure.database.threads import get_thread, thread_belongs_to_user

router = APIRouter(prefix="/api/threads", tags=["memory"])


def _validate_thread_access(
    thread_id: str,
    user_id: str | None,
    current: CurrentUser,
) -> dict:
    """Valide l'accès : thread existe + appartient au user courant.

    Le user_id ( query , rétrocompatibilité ) doit correspondre à
    la session — un simple retrait du param ne contourne plus rien
    car la décision vient de current.user_id ( admin excepté ).
    """
    init_db()
    thread = get_thread(thread_id)
    if thread is None:
        raise HTTPException(
            404, detail="Thread introuvable"
        )

    if not current.is_admin:
        if not thread_belongs_to_user(
            thread_id, current.user_id
        ):
            raise HTTPException(
                403,
                detail="Ce thread n'appartient pas à cet utilisateur",
            )
        if user_id is not None and user_id != current.user_id:
            raise HTTPException(
                403,
                detail="user_id ne correspond pas à la session",
            )
    return thread


@router.get("/{thread_id}/state", response_model=StateResponse)
def api_thread_state(
    thread_id: str,
    user_id: str | None = None,
    current: CurrentUser = Depends(get_current_user),
) -> StateResponse:
    """State courant : user_id, interactions, messages, dernier checkpoint."""
    _validate_thread_access(thread_id, user_id, current)
    state = get_thread_state(current.user_id, thread_id)
    if state is None:
        # Thread sans historique LangGraph (créé mais jamais utilisé)
        return StateResponse(
            user_id=current.user_id,
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
    thread_id: str,
    user_id: str | None = None,
    current: CurrentUser = Depends(get_current_user),
) -> list[CheckpointOut]:
    """Historique des checkpoints (timeline)."""
    _validate_thread_access(thread_id, user_id, current)
    history = get_thread_history(current.user_id, thread_id)
    return [CheckpointOut(**h) for h in history]
