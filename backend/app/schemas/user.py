# User Schemas — contrats /api/users (ex app/api/schemas.py).
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
    clerk_user_id: str | None = None
    role: str = "user"
    # MODE DEV UNIQUEMENT : token de session simulée pour les
    # suites de régression ("dev:<internal_user_id>"). Jamais
    # renseigné en mode clerk.
    dev_token: str | None = None


class ProfileOut(BaseModel):
    user_id: str
    name: str | None
    description: str | None
    exists: bool


class ProfileUpdate(BaseModel):
    """PUT /api/users/{user_id}/profile — champs autorisés uniquement."""

    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("user_id", check_fields=False)
    @classmethod
    def never_user_id(cls, v):
        # user_id vient uniquement du path — jamais du body
        if v is not None:
            raise ValueError("user_id n'est pas modifiable via le body")
        return v

    @field_validator("name", "description")
    @classmethod
    def strip_values(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        return v


__all__ = ["UserCreate", "UserOut", "ProfileOut", "ProfileUpdate"]
