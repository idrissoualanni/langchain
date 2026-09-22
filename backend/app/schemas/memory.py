# Memory Schemas — MemoryFacts v3 (ex app/api/schemas.py).
#
# Faits individuels par catégorie — mémoire longue durée cross-thread.
from pydantic import BaseModel, Field, field_validator


class MemoryFactOut(BaseModel):
    id: str
    category: str
    content: str
    source: str
    confidence: float
    created_at: str
    updated_at: str


class MemoryOverviewOut(BaseModel):
    user_id: str
    identity: dict
    facts_by_category: dict[str, list[MemoryFactOut]]
    total_facts: int
    categories: list[str]


def _check_category(v: str | None) -> str | None:
    """Valide une catégorie contre FACT_CATEGORIES (import lazy :
    app.schemas ne doit pas dépendre du service mémoire au import)."""
    if v is None:
        return None
    from app.services.memory.memory import FACT_CATEGORIES

    if v not in FACT_CATEGORIES:
        raise ValueError(
            f"Catégorie inconnue : {v}. "
            f"Catégories autorisées : {list(FACT_CATEGORIES)}"
        )
    return v


class MemoryFactCreate(BaseModel):
    """POST /api/users/{id}/memory — création manuelle d'un fait."""

    category: str = Field(..., max_length=50)
    content: str = Field(..., min_length=1, max_length=2000)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("category")
    @classmethod
    def valid_category(cls, v: str) -> str:
        return _check_category(v)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Le contenu ne peut pas être vide")
        return v.strip()


class MemoryFactUpdate(BaseModel):
    """PUT /api/users/{id}/memory/{fact_id} — update ciblé."""

    content: str | None = Field(
        default=None, min_length=1, max_length=2000
    )
    category: str | None = Field(default=None, max_length=50)

    @field_validator("category")
    @classmethod
    def valid_category(cls, v: str | None) -> str | None:
        return _check_category(v)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not v.strip():
            raise ValueError("Le contenu ne peut pas être vide")
        return v.strip()


__all__ = [
    "MemoryFactOut",
    "MemoryOverviewOut",
    "MemoryFactCreate",
    "MemoryFactUpdate",
]
