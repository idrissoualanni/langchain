# Routes Chat — POST /api/chat + GET /api/chat/stream (SSE)
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from app.agent.runner import run_agent, run_agent_stream
from app.api.schemas import ChatRequest, ChatResponse
from app.db.connections import init_db
from app.db.threads import get_thread, thread_belongs_to_user
from app.db.users import get_user

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _validate_chat(payload: ChatRequest) -> None:
    """Validation : user existe, thread existe, thread appartient au user."""
    init_db()

    if get_user(payload.user_id) is None:
        raise HTTPException(
            status_code=404,
            detail="Utilisateur introuvable",
        )

    thread = get_thread(payload.thread_id)
    if thread is None:
        raise HTTPException(
            status_code=404,
            detail="Thread introuvable",
        )

    # Sécurité : un utilisateur ne peut pas utiliser le thread d'un autre
    if not thread_belongs_to_user(
        payload.thread_id, payload.user_id
    ):
        raise HTTPException(
            status_code=403,
            detail="Ce thread n'appartient pas à cet utilisateur",
        )


@router.post("", response_model=ChatResponse)
def api_chat(payload: ChatRequest) -> ChatResponse:
    """Envoyer un message — réponse complète après le run."""
    _validate_chat(payload)
    result = run_agent(
        user_id=payload.user_id,
        thread_id=payload.thread_id,
        message=payload.message,
    )
    return ChatResponse(**result)


@router.get("/stream")
async def api_chat_stream(
    user_id: str,
    thread_id: str,
    message: str,
):
    """Envoyer un message — stream SSE des événements du pipeline.

    Événements : RUN_START, STATE_LOAD, USER_MESSAGE, ASSISTANT_MESSAGE,
    CHECKPOINT_SAVED, RUN_END (+ TOOL_START/TOOL_END/TOOL_ERROR temps réel
    via le bus d'événements pendant le run).
    """
    try:
        payload = ChatRequest(
            user_id=user_id,
            thread_id=thread_id,
            message=message,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=json.loads(exc.json())[0]["msg"],
        )

    _validate_chat(payload)

    async def gen():
        async for event in run_agent_stream(
            user_id=payload.user_id,
            thread_id=payload.thread_id,
            message=payload.message,
        ):
            # Format SSE textuel : event: X\ndata: {...}\n\n
            yield (
                f"event: {event.get('event', 'LOG')}\n"
                f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            )

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
