# Routes Chat — POST /api/chat + POST /api/chat/stream (SSE)
#
# Mission Identité :
#   - l'identité vient du Bearer token ( get_current_user )
#   - le user_id du BODY n'est plus une source d'identité : il est
#     VÉRIFIÉ contre l'utilisateur courant ( 403 si usurpation )
import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from app.services.agent.runner import run_agent, run_agent_stream
from app.logging.events import log_event
from app.schemas import ChatRequest, ChatResponse
from app.auth.resolver import CurrentUser, get_current_user
from app.infrastructure.database.connections import init_db
from app.infrastructure.database.threads import get_thread, thread_belongs_to_user
from app.core.rate_limit import limiter

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _validate_chat(
    payload: ChatRequest, current: CurrentUser
) -> None:
    """Validation : user existe, thread existe, thread au user.

    Mission Identité : le user_id du payload doit être CELUI DE LA
    SESSION ( anti-usurpation ) — un user_id d'autrui → 403, admin
    compris : un thread porte l'historique et la mémoire de son
    propriétaire, sur lesquels l'administration n'a aucun droit de
    lecture (AGENTS.md, Souveraineté).
    """
    init_db()

    # Anti-usurpation (§10) : le body ne définit pas l'identité
    if payload.user_id != current.user_id:
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
@limiter.limit("20/minute")
def api_chat(
    request: Request,
    # paramètre `response` OBLIGATOIRE pour le décorateur slowapi :
    # sans lui, _inject_headers(None, ...) lève sur chaque requête
    # ( la réponse finale n'étant pas une Response ). FastAPI le
    # peuple automatiquement.
    response: Response,
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
            # current.is_admin est DÉJÀ validé par get_current_user() :
            # le transmettre évite que le pipeline redérive un rôle en
            # comparant des identifiants (cf. l'ancien
            # user_id in ADMIN_CLERK_IDS, toujours faux).
            is_admin=current.is_admin,
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


@router.post("/stream")
@limiter.limit("20/minute")
async def api_chat_stream(
    request: Request,
    # `response` requis par le décorateur slowapi ( injection headers ),
    # cf. commentaire sur api_chat.
    response: Response,
    payload_obj: ChatRequest,
    current: CurrentUser = Depends(get_current_user),
):
    """Envoyer un message — stream SSE des événements du pipeline.

    POST + corps JSON, et non GET + query : un GET qui lance un run
    échappait au contrôle d'Origine (`enforce_origin` ne garde que les
    méthodes mutantes) alors que le cookie de session est SameSite=None,
    et le message de l'utilisateur finissait dans les journaux d'accès.

    Événements : RUN_START, STATE_LOAD, USER_MESSAGE, ASSISTANT_MESSAGE,
    CHECKPOINT_SAVED, RUN_END (+ TOOL_START/TOOL_END/TOOL_ERROR temps réel
    via le bus d'événements pendant le run).
    """
    _validate_chat(payload_obj, current)

    async def gen():
        # §47 : dernier rempart — si le stream lève (y compris dans le
        # post-traitement du runner), on n'envoie PAS de connexion coupée
        # nette : un événement ERROR générique est émis avant fermeture.
        try:
            async for event in run_agent_stream(
                user_id=payload_obj.user_id,
                thread_id=payload_obj.thread_id,
                message=payload_obj.message,
                model=payload_obj.model,
                workflow=payload_obj.workflow,
                payload=payload_obj.payload,
                # Même rôle résolu que le chemin JSON — l'UI Assistant
                # utilise le stream, c'est donc LE chemin qui compte
                # réellement pour le contournement admin du RAG.
                is_admin=current.is_admin,
            ):
                # Format SSE textuel : event: X\ndata: {...}\n\n
                yield (
                    f"event: {event.get('event', 'LOG')}\n"
                    f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                )
        except Exception as exc:  # noqa: BLE001 — §47, cause dans les logs
            log_event(
                "ERROR",
                level="ERROR",
                message=f"Stream error: {exc}",
                user_id=payload_obj.user_id,
                thread_id=payload_obj.thread_id,
            )
            yield (
                "event: ERROR\n"
                "data: "
                + json.dumps(
                    {
                        "event": "ERROR",
                        "level": "ERROR",
                        "user_id": payload_obj.user_id,
                        "thread_id": payload_obj.thread_id,
                        "message": "Stream interrompu — cause technique journalisée.",
                    },
                    ensure_ascii=False,
                )
                + "\n\n"
            )

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
