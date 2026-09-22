# Routes Users — Mission Identité : l'identité vient de la SESSION
# (get_current_user), jamais du client.
#
# La seule création de user restante est le PROVISIONING interne au
# login (app/auth/resolver.py). POST /api/users PUBLIC est retiré :
# plus personne ne crée un user en fournissant juste un nom.
#
# Memory/Profile : user_id de chemin VALIDÉ contre l'utilisateur
# courant (ownership) — user A ne lit/modifie/supprime JAMAIS les
# facts de B. Admin : accès complet (§8).
from fastapi import APIRouter, Depends, HTTPException, Query

from app.services.memory.memory import (
    delete_fact,
    list_facts,
    memory_overview_for_api,
    read_profile_for_api,
    save_fact,
    search_facts,
    update_fact,
    write_profile,
)
from app.schemas import (
    MemoryFactCreate,
    MemoryFactOut,
    MemoryFactUpdate,
    MemoryOverviewOut,
    ProfileOut,
    ProfileUpdate,
    UserCreate,
    UserOut,
)
from app.auth.resolver import CurrentUser, get_current_user
from app.config import ADMIN_CLERK_IDS, AUTH_MODE
from app.infrastructure.database import users as users_db
from app.infrastructure.database.connections import init_db
from app.infrastructure.database.users import get_user, list_users
from app.logging.events import log_event

router = APIRouter(prefix="/api/users", tags=["users"])


def _require_owner_or_admin(
    user_id: str, current: CurrentUser
) -> None:
    """Ownership : le user_id du chemin doit être le sien (ou admin).

    404 (et non 403) si le user n'existe pas ; 403 si existe mais
    appartient à autrui — convention anti-énumération.
    """
    init_db()
    if current.is_admin:
        return
    if user_id != current.user_id:
        target = get_user(user_id)
        if target is None:
            raise HTTPException(
                status_code=404, detail="Utilisateur introuvable"
            )
        raise HTTPException(
            status_code=403,
            detail="Accès refusé : ressource d'un autre utilisateur",
        )


@router.get("/me", response_model=UserOut)
def api_me(current: CurrentUser = Depends(get_current_user)) -> UserOut:
    """Utilisateur COURANT résolu depuis la session (Clerk).

    C'est LA route d'identité du frontend : remplace UserSelector.
    """
    u = get_user(current.user_id)
    if u is None:
        raise HTTPException(404, "Utilisateur interne introuvable")
    return UserOut(**u)


# ------------------------------------------------------------------
# Provisioning de TEST — MODE DEV UNIQUEMENT
# ------------------------------------------------------------------
# En mode dev ( AUTH_MODE=dev , développement local sans clés
# Clerk ) les suites de régression historiques créent leurs users
# de test via POST /api/users. Ce endpoint n'existe PLUS en mode
# clerk : l'inscription passe par Clerk ( SignUp ) puis le
# resolver provisionne l'utilisateur interne au premier login.
# Le user_id du body N'EST JAMAIS une source d'identité — le
# token dev:devuuid sert de session simulée pour les tests.
if AUTH_MODE == "dev":

    @router.post("", response_model=UserOut, status_code=201)
    def api_create_user_dev(payload: UserCreate) -> UserOut:
        """[DEV SEULEMENT] Créer un user de test + son token dev."""
        init_db()
        # Test admin en dev : un nom présent dans ADMIN_CLERK_IDS
        # (ex: "dev-admin") est provisionné avec le rôle admin.
        role = "admin" if payload.name in ADMIN_CLERK_IDS else "user"
        user = users_db.create_user(payload.name, role=role)
        log_event(
            "AUTH_DEV_USER",
            message=f"Dev user provisioned (test): {payload.name} (role={role})",
            user_id=user["user_id"],
        )
        return UserOut(
            **user,
            dev_token=f"dev:{user['user_id']}",
        )


@router.get("", response_model=list[UserOut])
def api_list_users(
    current: CurrentUser = Depends(get_current_user),
) -> list[UserOut]:
    """Lister les utilisateurs — ADMIN uniquement (§9)."""
    if not current.is_admin:
        raise HTTPException(403, "Réservé aux administrateurs")
    return [UserOut(**u) for u in list_users()]


@router.get("/{user_id}", response_model=UserOut)
def api_get_user(
    user_id: str,
    current: CurrentUser = Depends(get_current_user),
) -> UserOut:
    """Obtenir un utilisateur — soi-même ou admin."""
    _require_owner_or_admin(user_id, current)
    user = get_user(user_id)
    if user is None:
        raise HTTPException(
            404, "Utilisateur introuvable"
        )
    return UserOut(**user)


# ------------------------------------------------------------------
# Mémoire longue durée — profil utilisateur (cross-thread)
# ------------------------------------------------------------------


@router.get("/{user_id}/profile", response_model=ProfileOut)
def api_get_profile(
    user_id: str,
    current: CurrentUser = Depends(get_current_user),
) -> ProfileOut:
    """Lire le profil longue durée (ownership vérifié)."""
    _require_owner_or_admin(user_id, current)
    return ProfileOut(**read_profile_for_api(user_id))


@router.put("/{user_id}/profile", response_model=ProfileOut)
def api_update_profile(
    user_id: str,
    payload: ProfileUpdate,
    current: CurrentUser = Depends(get_current_user),
) -> ProfileOut:
    """Créer/modifier le profil — ownership vérifié."""
    _require_owner_or_admin(user_id, current)

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
# MemoryFacts v3 — faits individuels par catégorie (ownership)
# ------------------------------------------------------------------


@router.get("/{user_id}/memory", response_model=MemoryOverviewOut)
def api_get_memory(
    user_id: str,
    current: CurrentUser = Depends(get_current_user),
) -> MemoryOverviewOut:
    """Vue complète de la mémoire — ownership vérifié."""
    _require_owner_or_admin(user_id, current)
    return MemoryOverviewOut(**memory_overview_for_api(user_id))


@router.get("/{user_id}/memory/facts", response_model=list[MemoryFactOut])
def api_list_facts(
    user_id: str,
    category: str | None = Query(default=None),
    current: CurrentUser = Depends(get_current_user),
) -> list[MemoryFactOut]:
    """Liste les faits — ownership vérifié."""
    _require_owner_or_admin(user_id, current)
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
    current: CurrentUser = Depends(get_current_user),
) -> list[MemoryFactOut]:
    """Recherche les faits — ownership vérifié."""
    _require_owner_or_admin(user_id, current)
    facts = search_facts(user_id, q)
    return [MemoryFactOut(**f) for f in facts]


@router.post(
    "/{user_id}/memory/facts",
    response_model=MemoryFactOut,
    status_code=201,
)
def api_create_fact(
    user_id: str,
    payload: MemoryFactCreate,
    current: CurrentUser = Depends(get_current_user),
) -> MemoryFactOut:
    """Crée un fait — ownership vérifié."""
    _require_owner_or_admin(user_id, current)
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
    user_id: str,
    fact_id: str,
    payload: MemoryFactUpdate,
    current: CurrentUser = Depends(get_current_user),
) -> MemoryFactOut:
    """Modifie UN fait — ownership vérifié."""
    _require_owner_or_admin(user_id, current)
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
def api_delete_fact(
    user_id: str,
    fact_id: str,
    current: CurrentUser = Depends(get_current_user),
) -> dict:
    """Supprime UN fait — ownership vérifié."""
    _require_owner_or_admin(user_id, current)
    try:
        return delete_fact(user_id, fact_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
