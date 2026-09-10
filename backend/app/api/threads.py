# Routes Threads
from fastapi import APIRouter, HTTPException

from app.api.schemas import ThreadCreate, ThreadOut
from app.db.connections import init_db
from app.db.threads import (
    create_thread,
    get_thread,
    list_threads,
)
from app.db.users import get_user

router = APIRouter(prefix="/api", tags=["threads"])


@router.post(
    "/users/{user_id}/threads",
    response_model=ThreadOut,
    status_code=201,
)
def api_create_thread(user_id: str, payload: ThreadCreate) -> ThreadOut:
    """Créer un thread pour un utilisateur — UUID backend."""
    init_db()
    if get_user(user_id) is None:
        raise HTTPException(
            status_code=404,
            detail="Utilisateur introuvable",
        )
    thread = create_thread(user_id, payload.name)
    return ThreadOut(**thread)


@router.get(
    "/users/{user_id}/threads", response_model=list[ThreadOut]
)
def api_list_threads(user_id: str) -> list[ThreadOut]:
    """Lister les threads d'un utilisateur."""
    init_db()
    if get_user(user_id) is None:
        raise HTTPException(
            status_code=404,
            detail="Utilisateur introuvable",
        )
    return [ThreadOut(**t) for t in list_threads(user_id)]


@router.get("/threads/{thread_id}", response_model=ThreadOut)
def api_get_thread(thread_id: str) -> ThreadOut:
    """Obtenir les informations d'un thread."""
    init_db()
    thread = get_thread(thread_id)
    if thread is None:
        raise HTTPException(
            status_code=404, detail="Thread introuvable"
        )
    return ThreadOut(**thread)
