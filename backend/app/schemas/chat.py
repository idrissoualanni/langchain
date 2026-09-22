# Chat Schemas — contrat /api/chat (ex app/api/schemas.py).
from pydantic import BaseModel, Field, field_validator

from app.schemas.common import valid_uuid


class ChatRequest(BaseModel):
    # Mission Identité : user_id/thread_id restent au contrat pour
    # la rétrocompatibilité du format, MAIS l'identité vient du
    # Bearer token (get_current_user). Le user_id fourni ici est
    # VÉRIFIÉ contre l'utilisateur courant (403 si usurpation) —
    # il ne définit JAMAIS qui est l'utilisateur.
    user_id: str
    thread_id: str
    message: str = Field(..., min_length=1, max_length=10_000)
    # Mission Assistant UI (ModelSelector) : modèle Ollama optionnel.
    # None/absent → modèle par défaut (MODEL_NAME, env). Aucun autre
    # comportement backend ne dépend de ce champ.
    model: str | None = Field(default=None, max_length=100)
    # Composer (@mentions → termes) : hint de workflow optionnel. Validé
    # contre KNOWN_WORKFLOWS par le WORKFLOW_ROUTER ; une valeur inconnue
    # est ignorée + tracée (jamais silencieuse, jamais d'erreur 400 — le
    # message reste traité sur la chaîne principale).
    workflow: str | None = Field(default=None, max_length=50)
    # Composer (@mentions → termes) : entrée structurée du workflow
    # (§8 SubgraphInput). Ex : {"research_mode": "deep-research"} pour
    # orienter la synthèse du ResearchSubgraph, {"source_url": …} pour
    # le VideoSubgraph. Dict plat de scalaires, clés/valeurs bornées.
    # Jamais d'exécution de code, jamais de secret (§41).
    payload: dict = Field(default_factory=dict)

    @field_validator("user_id")
    @classmethod
    def valid_user_id(cls, v: str) -> str:
        return valid_uuid(v, "user_id")

    @field_validator("thread_id")
    @classmethod
    def valid_thread_id(cls, v: str) -> str:
        return valid_uuid(v, "thread_id")

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Le message ne peut pas être vide")
        return v.strip()

    @field_validator("model")
    @classmethod
    def valid_model(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class ChatResponse(BaseModel):
    response: str
    # V6.7 : réponse structurée (contrat AgentResponse) — le
    # texte brut reste pour rétrocompatibilité.
    agent_response: dict | None = None
    user_id: str
    thread_id: str
    interaction_count: int


__all__ = ["ChatRequest", "ChatResponse"]
