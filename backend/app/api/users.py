# Routes Users
from fastapi import APIRouter, HTTPException, Query

from app.agent.memory import (
    delete_fact,
    list_facts,
    memory_overview_for_api,
    read_profile_for_api,
    save_fact,
    search_facts,
    update_fact,
    write_profile,
)
from app.api.schemas import (
    MemoryFactCreate,
    MemoryFactOut,
    MemoryFactUpdate,
    MemoryOverviewOut,
    ProfileOut,
    ProfileUpdate,
    UserCreate,
    UserOut,
)
from app.db.connections import init_db
from app.db.users import create_user, get_user, list_users

router = APIRouter(prefix="/api/users", tags=["users"])


@router.post("", response_model=UserOut, status_code=201)
def api_create_user(payload: UserCreate) -> UserOut:
    """Créer un utilisateur — UUID généré côté backend."""
    init_db()
    user = create_user(payload.name)
    return UserOut(**user)


@router.get("", response_model=list[UserOut])
def api_list_users() -> list[UserOut]:
    """Lister tous les utilisateurs."""
    init_db()
    return [UserOut(**u) for u in list_users()]


@router.get("/{user_id}", response_model=UserOut)
def api_get_user(user_id: str) -> UserOut:
    """Obtenir un utilisateur par ID."""
    init_db()
    user = get_user(user_id)
    if user is None:
        raise HTTPException(
            status_code=404, detail="Utilisateur introuvable"
        )
    return UserOut(**user)


# ------------------------------------------------------------------
# Mémoire longue durée — profil utilisateur (cross-thread)
# ------------------------------------------------------------------


@router.get("/{user_id}/profile", response_model=ProfileOut)
def api_get_profile(user_id: str) -> ProfileOut:
    """Lire le profil longue durée de l'utilisateur (store SqliteStore)."""
    init_db()
    if get_user(user_id) is None:
        raise HTTPException(
            status_code=404, detail="Utilisateur introuvable"
        )
    return ProfileOut(**read_profile_for_api(user_id))


@router.put("/{user_id}/profile", response_model=ProfileOut)
def api_update_profile(
    user_id: str, payload: ProfileUpdate
) -> ProfileOut:
    """Créer/modifier le profil longue durée — champs name/description uniquement."""
    init_db()
    if get_user(user_id) is None:
        raise HTTPException(
            status_code=404, detail="Utilisateur introuvable"
        )

    fields = payload.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(
            status_code=422,
            detail="Au moins un champ (name ou description) est requis",
        )

    try:
        profile = write_profile(user_id, fields)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return ProfileOut(
        user_id=user_id,
        name=profile["name"],
        description=profile["description"],
        exists=True,
    )


# ------------------------------------------------------------------
# MemoryFacts v3 — faits individuels par catégorie
# ------------------------------------------------------------------


@router.get("/{user_id}/memory", response_model=MemoryOverviewOut)
def api_get_memory(user_id: str) -> MemoryOverviewOut:
    """Vue complète de la mémoire : profil + faits groupés par catégorie."""
    init_db()
    if get_user(user_id) is None:
        raise HTTPException(
            status_code=404, detail="Utilisateur introuvable"
        )
    return MemoryOverviewOut(**memory_overview_for_api(user_id))


@router.get("/{user_id}/memory/facts", response_model=list[MemoryFactOut])
def api_list_facts(
    user_id: str,
    category: str | None = Query(default=None),
) -> list[MemoryFactOut]:
    """Liste les faits, filtrable par catégorie."""
    init_db()
    if get_user(user_id) is None:
        raise HTTPException(
            status_code=404, detail="Utilisateur introuvable"
        )
    try:
        facts = list_facts(user_id, category)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return [MemoryFactOut(**f) for f in facts]


@router.get(
    "/{user_id}/memory/search", response_model=list[MemoryFactOut]
)
def api_search_memory(
    user_id: str,
    q: str = Query(..., min_length=1, max_length=500),
) -> list[MemoryFactOut]:
    """Recherche les faits pertinents pour une requête."""
    init_db()
    if get_user(user_id) is None:
        raise HTTPException(
            status_code=404, detail="Utilisateur introuvable"
        )
    facts = search_facts(user_id, q)
    return [MemoryFactOut(**f) for f in facts]


@router.post(
    "/{user_id}/memory/facts",
    response_model=MemoryFactOut,
    status_code=201,
)
def api_create_fact(
    user_id: str, payload: MemoryFactCreate
) -> MemoryFactOut:
    """Crée manuellement un fait (avec déduplication automatique)."""
    init_db()
    if get_user(user_id) is None:
        raise HTTPException(
            status_code=404, detail="Utilisateur introuvable"
        )
    try:
        fact = save_fact(
            user_id,
            payload.category,
            payload.content,
            source="user",
            confidence=payload.confidence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return MemoryFactOut(**fact)


@router.put(
    "/{user_id}/memory/facts/{fact_id}",
    response_model=MemoryFactOut,
)
def api_update_fact(
    user_id: str, fact_id: str, payload: MemoryFactUpdate
) -> MemoryFactOut:
    """Modifie UN fait précis — les autres restent intacts."""
    init_db()
    if get_user(user_id) is None:
        raise HTTPException(
            status_code=404, detail="Utilisateur introuvable"
        )
    try:
        fact = update_fact(
            user_id,
            fact_id,
            content=payload.content,
            category=payload.category,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return MemoryFactOut(**fact)


@router.delete(
    "/{user_id}/memory/facts/{fact_id}",
    status_code=200,
)
def api_delete_fact(user_id: str, fact_id: str) -> dict:
    """Supprime UN fait précis — les autres restent intacts."""
    init_db()
    if get_user(user_id) is None:
        raise HTTPException(
            status_code=404, detail="Utilisateur introuvable"
        )
    try:
        return delete_fact(user_id, fact_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
