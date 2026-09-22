# Routes Context V5 — preview du contexte (§44).
#
# POST /api/context/preview → contexte + prompt SANS LLM.
# Alias canonique V5 de /api/subjects/preview/context (l'ancienne
# route reste pour le frontend — même handler, même réponse).
from fastapi import APIRouter

from app.schemas import (
    ContextPreviewRequest,
    ContextPreviewResponse,
)
from app.api.subjects import build_context_preview

router = APIRouter(prefix="/api/context", tags=["context"])


@router.post("/preview", response_model=ContextPreviewResponse)
def api_context_preview(
    payload: ContextPreviewRequest,
) -> ContextPreviewResponse:
    """Prévisualise le contexte + prompt SANS appeler le LLM (§44).

    Expose la sélection interne (routing, subject, knowledge,
    tools, mémoire, thread) — route dev, à protéger en production.
    """
    return build_context_preview(payload)
