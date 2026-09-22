# Routes Chat — POST /api/chat + GET /api/chat/stream (SSE)
#
# Mission Identité :
#   - l'identité vient du Bearer token ( get_current_user )
#   - le user_id du BODY n'est plus une source d'identité : il est
#     VÉRIFIÉ contre l'utilisateur courant ( 403 si usurpation )
#   - SSE : user_id/thread_id/messages restent en query ( identité
#     via Authorization header — JAMAIS de token en URL , §17 )
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from app.services.agent.runner import run_agent, run_agent_stream
from app.schemas import ChatRequest, ChatResponse
from app.auth.resolver import CurrentUser, get_current_user
from app.infrastructure.database.connections import init_db
from app.infrastructure.database.threads import get_thread, thread_belongs_to_user
from app.logging.events import log_event

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _validate_chat(
    payload: ChatRequest, current: CurrentUser
) -> None:
    """Validation : user existe, thread existe, thread au user.

    Mission Identité : le user_id du payload doit être CELUI DE LA
    SESSION ( anti-usurpation ) — un user_id d'autrui → 403.
    """
    init_db()

    # Anti-usurpation (§10) : le body ne définit pas l'identité
    if not current.is_admin and payload.user_id != current.user_id:
        raise HTTPException(
            status_code=403,
            detail="user_id ne correspond pas à la session",
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
def api_chat(
    payload: ChatRequest,
    current: CurrentUser = Depends(get_current_user),
) -> ChatResponse:
    """Envoyer un message — réponse complète après le run."""
    _validate_chat(payload, current)
    try:
        result = run_agent(
            user_id=payload.user_id,
            thread_id=payload.thread_id,
            message=payload.message,
            model=payload.model,
            workflow=payload.workflow,
            payload=payload.payload,
        )
    except Exception:  # noqa: BLE001 — 500 contrôlé (jamais stack leak)
        log_event(
            "CHAT_RUN_ERROR",
            level="ERROR",
            message=(
                f"run_agent en échec | thread={payload.thread_id} | "
                f"user={payload.user_id}"
            ),
            user_id=payload.user_id,
            thread_id=payload.thread_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Le run agent a échoué — réessayez ou consultez les logs.",
        )
    return ChatResponse(**result)


@router.get("/stream")
async def api_chat_stream(
    user_id: str,
    thread_id: str,
    message: str,
    model: str | None = None,
    workflow: str | None = None,
    payload: str | None = None,
    current: CurrentUser = Depends(get_current_user),
):
    """Envoyer un message — stream SSE des événements du pipeline.

    Mission Identité (§17) : l'identité vient du HEADER
    Authorization Bearer ( JAMAIS du query param ). user_id en
    query n'est qu'une VÉRIFICATION anti-usurpation — 403 s'il ne
    correspond pas à la session.

    payload : JSON string (query param) — entrée structurée du
    workflow (§8). Un JSON invalide est ignoré + tracé, jamais un
    400 (le run continue sur la chaîne principale).

    Événements : RUN_START, STATE_LOAD, USER_MESSAGE, ASSISTANT_MESSAGE,
    CHECKPOINT_SAVED, RUN_END (+ TOOL_START/TOOL_END/TOOL_ERROR temps réel
    via le bus d'événements pendant le run).
    """
    parsed_payload: dict = {}
    if payload:
        try:
            decoded = json.loads(payload)
            if isinstance(decoded, dict):
                parsed_payload = decoded
            else:
                log_event(
                    "CHAT_PAYLOAD_IGNORED",
                    level="WARNING",
                    message="payload JSON n'est pas un object — ignoré",
                )
        except json.JSONDecodeError:
            log_event(
                "CHAT_PAYLOAD_IGNORED",
                level="WARNING",
                message="payload JSON invalide — ignoré",
            )

    try:
        payload_obj = ChatRequest(
            user_id=user_id,
            thread_id=thread_id,
            message=message,
            model=model,
            workflow=workflow,
            payload=parsed_payload,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=json.loads(exc.json())[0]["msg"],
        )

    _validate_chat(payload_obj, current)

    async def gen():
        async for event in run_agent_stream(
            user_id=payload_obj.user_id,
            thread_id=payload_obj.thread_id,
            message=payload_obj.message,
            model=payload_obj.model,
            workflow=payload_obj.workflow,
            payload=payload_obj.payload,
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
