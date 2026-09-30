# User Schemas — contrats /api/users (ex app/api/schemas.py).
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Le nom ne peut pas être vide")
        return v.strip()


class UserOut(BaseModel):
    user_id: str
    name: str
    created_at: str
    # Mission Identité — infos session (optionnelles)
    # Claim `sub` du fournisseur d'identité (Neon Auth en mode neon).
    # Conservé pour tracer la session vers son origine externe.
    external_user_id: str | None = None
    role: str = "user"
    # MODE DEV UNIQUEMENT : token de session simulée pour les
    # suites de régression ("dev:<internal_user_id>"). Jamais
    # renseigné en mode neon.
    dev_token: str | None = None


class RoleUpdate(BaseModel):
    """PUT /api/admin/users/{user_id}/role — nouveau rôle d'un utilisateur.

    L'énumération Literal ferme le contrat : seuls 'admin' et 'user'
    sont acceptés, toute autre valeur est rejetée en 422 par FastAPI.
    La base `users.role` est l'autorité unique au runtime (ADR-023) :
    ce schéma est le canal d'écriture explicite qui remplace
    l'auto-persistance d'écart retirée du resolver.
    """

    role: Literal["admin", "user"] = Field(...)


class ProfileOut(BaseModel):
    """Profil longue durée + infos du compte (public.users).

    Le profil en lui-même (name/description) vit dans le store mémoire
    LangGraph ; les infos du compte (role, created_at, external_user_id,
    nom d'identité) vivent dans public.users. Les regrouper ici évite
    au frontend un second aller-retour pour afficher la page de profil.
    """

    user_id: str
    name: str | None
    description: str | None
    exists: bool
    # --- infos du compte (public.users) — optionnelles par compatibilité
    # (un profil peut exister pour un user dont la ligne a disparu). ---
    account_name: str | None = None
    role: str | None = None
    created_at: str | None = None
    external_user_id: str | None = None


class ProfileUpdate(BaseModel):
    """PUT /api/users/{user_id}/profile — champs autorisés uniquement.

    user_id vient du PATH, jamais du body : le contrat ne le déclare
    pas dans le modèle, donc un champ inconnu est rejeté en 422 par
    FastAPI. (Aucun validateur « garde-fou » n'est nécessaire : un
    champ absent du modèle ne peut pas être reçu.)
    """

    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str | None) -> str | None:
        """Un name EXPLICITEMENT fourni ne peut pas être vide.

        Pourquoi : avant, "" était transformé en None puis exclu de
        model_dump(exclude_none=True) → la mise à jour était
        silencieusement ignorée. On rejette en 422 à la place : un
        nom affiché vide est une erreur utilisateur, pas une fausse
        réussite. None (champ absent) reste accepté pour l'update
        partiel.
        """
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("Le nom ne peut pas être vide")
        return v

    @field_validator("description")
    @classmethod
    def strip_description(cls, v: str | None) -> str | None:
        # La description peut être vidée : strip puis None si vide
        # (l'update partiel ignore les None, donc "" ne peut pas
        # effacer — on laisse la valeur telle quelle si vide).
        if v is None:
            return None
        v = v.strip()
        if not v:
            return ""
        return v


__all__ = ["RoleUpdate", "UserCreate", "UserOut", "ProfileOut", "ProfileUpdate"]
