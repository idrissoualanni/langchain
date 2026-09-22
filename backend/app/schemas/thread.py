# Thread Schemas — contrats /api/threads (ex app/api/schemas.py).
from pydantic import BaseModel, Field, field_validator


class ThreadCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Le nom du thread ne peut pas être vide")
        return v.strip()


class ThreadOut(BaseModel):
    thread_id: str
    user_id: str
    name: str
    created_at: str


class ThreadRename(BaseModel):
    """PUT /api/threads/{thread_id} — renommage (assistant-ui)."""

    name: str = Field(..., min_length=1, max_length=150)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Le nom du thread ne peut pas être vide")
        return v.strip()


class MessageOut(BaseModel):
    type: str
    content: str
    tool_calls: list[dict] | None = None


class StateResponse(BaseModel):
    user_id: str
    thread_id: str
    interaction_count: int
    message_count: int
    messages: list[MessageOut]


class CheckpointOut(BaseModel):
    checkpoint_id: str | None
    created_at: str
    message_count: int
    interaction_count: int
    summary: str
    # V6.8 (audit §62 G.3) : nature du checkpoint — le frontend
    # consomme ce champ structuré au lieu de parser le summary.
    kind: str = "state"


__all__ = [
    "ThreadCreate",
    "ThreadOut",
    "ThreadRename",
    "MessageOut",
    "StateResponse",
    "CheckpointOut",
]
