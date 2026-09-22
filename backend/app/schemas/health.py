# Health Schemas — contrat /api/health (ex app/api/schemas.py).
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    ollama: bool
    langgraph: bool
    sqlite: bool
    model: str


__all__ = ["HealthResponse"]
