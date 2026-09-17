# Routes Threads — Mission Identité : ownership dérivé de la SESSION
#
# Corrigé depuis l'audit (§12) :
#   GET  /api/threads/{id}      → ne divulgue plus le user_id
#                                 d'autrui (ownership 403)
#   PUT  /api/threads/{id}      → renommage réservé au propriétaire
#   POST /api/users/{uid}/threads → le propriétaire est TOUJOURS
#                                 l'utilisateur courant (403 si
#                                 uid != current)
#
# Le thread_id reste la clé technique LangGraph ( checkpointer ) —
# générée côté backend, inchangée.
from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.schemas import ThreadCreate, ThreadOut, ThreadRename
from app.auth.resolver import CurrentUser, get_current_user
from app.db.connections import init_db
from app.db.threads import (
    create_thread,
    delete_thread,
    get_thread,
    list_threads,
    rename_thread,
    thread_belongs_to_user,
)
from app.db.users import get_user

router = APIRouter(prefix="/api", tags=["threads"])


def _require_thread_owner(
    thread_id: str, current: CurrentUser
) -> dict:
    """Thread existe + appartient à l'utilisateur courant (ou admin).

    404 si inexistant ; 403 si existant mais d'autrui (sauf admin).
    """
    init_db()
    thread = get_thread(thread_id)
    if thread is None:
        raise HTTPException(
            404, detail="Thread introuvable"
        )
    if not current.is_admin and not thread_belongs_to_user(
        thread_id, current.user_id
    ):
        raise HTTPException(
            status_code=403,
            detail="Ce thread n'appartient pas à cet utilisateur",
        )
    return thread


@router.post(
    "/users/{user_id}/threads",
    response_model=ThreadOut,
    status_code=201,
)
def api_create_thread(
    user_id: str,
    payload: ThreadCreate,
    current: CurrentUser = Depends(get_current_user),
) -> ThreadOut:
    """Créer un thread — propriétaire = utilisateur COURANT (§13).

    Le user_id du chemin doit être le sien (ou admin) ; le client
    ne choisit plus le propriétaire.
    """
    init_db()
    if current.is_admin and user_id != current.user_id:
        # admin : peut créer pour autrui (gestion §8)
        if get_user(user_id) is None:
            raise HTTPException(
                404, detail="Utilisateur introuvable"
            )
    elif user_id != current.user_id:
        raise HTTPException(
            status_code=403,
            detail="Création refusée : identité différente",
        )
    thread = create_thread(user_id, payload.name)
    return ThreadOut(**thread)


@router.get(
    "/users/{user_id}/threads", response_model=list[ThreadOut]
)
def api_list_threads(
    user_id: str,
    current: CurrentUser = Depends(get_current_user),
) -> list[ThreadOut]:
    """Lister les threads — uniquement les SIENS (§11)."""
    init_db()
    if not current.is_admin and user_id != current.user_id:
        # 404 : ne pas révéler l'existence d'un autre compte
        raise HTTPException(
            404, detail="Utilisateur introuvable"
        )
    if get_user(user_id) is None:
        raise HTTPException(
            404, detail="Utilisateur introuvable"
        )
    return [ThreadOut(**t) for t in list_threads(user_id)]


@router.get("/threads/{thread_id}", response_model=ThreadOut)
def api_get_thread(
    thread_id: str,
    current: CurrentUser = Depends(get_current_user),
) -> ThreadOut:
    """Obtenir un thread — propriétaire ou admin (§12).

    L'audit notait une fuite : ce GET divulguait le user_id
    propriétaire à n'importe qui. Désormais 403 pour autrui.
    """
    thread = _require_thread_owner(thread_id, current)
    return ThreadOut(**thread)


@router.put("/threads/{thread_id}", response_model=ThreadOut)
def api_rename_thread(
    thread_id: str,
    payload: ThreadRename,
    current: CurrentUser = Depends(get_current_user),
) -> ThreadOut:
    """Renommer un thread — propriétaire ou admin (§12).

    L'audit notait un renommage cross-user possible (aucune
    vérification). Désormais 403 pour autrui.
    """
    _require_thread_owner(thread_id, current)
    thread = rename_thread(thread_id, payload.name)
    if thread is None:
        raise HTTPException(
            404, detail="Thread introuvable"
        )
    return ThreadOut(**thread)


@router.delete("/threads/{thread_id}", status_code=204)
def api_delete_thread(
    thread_id: str,
    current: CurrentUser = Depends(get_current_user),
) -> Response:
    """Supprimer un thread — propriétaire ou admin (§12)."""
    _require_thread_owner(thread_id, current)
    delete_thread(thread_id)
    return Response(status_code=204)
