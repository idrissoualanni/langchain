# Routes Admin Users — gestion des rôles (promotion / rétrogradation).
#
# ADR-023 : `users.role` (base) est l'autorité UNIQUE au runtime ;
# ADMIN_EXTERNAL_IDS (env) n'est qu'un bootstrap initial. L'ancienne
# auto-persistance d'écart (set_user_role appelé à la volée depuis le
# resolver) a été retirée parce qu'elle MASQUAIT les divergences de
# configuration. La conséquence assumée : le changement de rôle doit
# passer par un canal explicite — cette route admin, ou un UPDATE SQL.
#
#   PUT /api/admin/users/{user_id}/role  body {role: "admin"|"user"}
#
# Sécurité : réservé aux admins (require_admin). Un admin ne peut pas
# modifier son PROPRE rôle : s'il se rétrogradait, mais aussi s'il
# se promouvait... il est déjà admin. L'interdiction d'auto-modification
# protège surtout contre le lockout accidentel (le dernier admin se
# retire admin → plus personne ne peut administrer).
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.resolver import CurrentUser, require_admin
from app.infrastructure.database import users as users_db
from app.schemas import RoleUpdate, UserOut

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


@router.put("/{user_id}/role", response_model=UserOut)
def admin_set_user_role(
    user_id: str,
    payload: RoleUpdate,
    current_user: CurrentUser = Depends(require_admin),
) -> UserOut:
    """Change le rôle d'un utilisateur (admin uniquement).

    - `user_id` : identifiant interne (UUID) de l'utilisateur ciblé.
    - `role` : 'admin' ou 'user' (littéral, rejet 422 par le schéma).
    - 404 si l'utilisateur ciblé n'existe pas.
    - 403 si le demandeur n'est pas admin (géré par require_admin).
    - 422 si le demandeur cible son propre rôle.

    Le nouvel état est appliqué immédiatement en base : la prochaine
    requête `GET /api/users/me` de l'utilisateur ciblé reflétera le
    nouveau rôle (AdminGate frontend s'aligne tout seul).
    """
    # Anti-lockout : on refuse l'auto-modification. Sans cette garde,
    # un admin pourrait se rétrograder — et s'il est le seul admin,
    # le système n'a plus aucun administrateur pour corriger la
    # situation. La modification d'un rôle passe TOUJOURS par un
    # tiers admin (ou une intervention SQL directe).
    if user_id == current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Un admin ne peut pas modifier son propre rôle "
            "(anti-lockout) — demandez à un autre admin ou agissez en SQL.",
        )

    # Vérifie l'existence AVANT d'écrire : un UPDATE silencieux sur un
    # user inconnu ferait croire à tort que la cible a été modifiée.
    target = users_db.get_user(user_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utilisateur introuvable",
        )

    # La mise à jour est immédiate et journalisée (USER_ROLE_SET) dans
    # set_user_role — ne pas dupliquer le log ici.
    users_db.set_user_role(user_id, payload.role)

    # Relecture pour renvoyer l'état effectif (source de vérité = base).
    updated = users_db.get_user(user_id)
    return UserOut(**updated)