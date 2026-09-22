# Routes Context V5 — preview du contexte (§44).
#
# POST /api/context/preview → contexte + prompt SANS LLM.
# Alias canonique V5 de /api/subjects/preview/context (l'ancienne
# route reste pour le frontend — même handler, même réponse).
#
# Sécurité (§47 : jamais exposer le system prompt / la mémoire privée) :
# la preview expose la SÉLECTION INTERNE du user (routing, knowledge,
# mémoire, prompt) → ownership vérifié comme les autres routes : on ne
# prévisualise que PROPRE contexte (ou admin). Client auth nécessaire.
from fastapi import APIRouter, Depends, HTTPException

from app.schemas import (
    ContextPreviewRequest,
    ContextPreviewResponse,
)
from app.api.subjects import build_context_preview
from app.auth.resolver import CurrentUser, get_current_user

router = APIRouter(prefix="/api/context", tags=["context"])


@router.post("/preview", response_model=ContextPreviewResponse)
def api_context_preview(
    payload: ContextPreviewRequest,
    current: CurrentUser = Depends(get_current_user),
) -> ContextPreviewResponse:
    """Prévisualise le contexte + prompt SANS appeler le LLM (§44).

    Ownership vérifié : le user_id du body doit être le sien (ou
    admin) — voir build_context_preview.
    """
    return build_context_preview(payload, current)
