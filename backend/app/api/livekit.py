"""
LiveKit API Endpoints

Endpoints pour la gestion des sessions LiveKit (voice/video).
"""

from fastapi import APIRouter, Depends, HTTPException
import json
from livekit.api import (
    CreateAgentDispatchRequest,
    CreateRoomRequest,
    LiveKitAPI,
)
from livekit.protocol.agent import JobStatus
from pydantic import BaseModel
from typing import Any, Optional

from app.livekit.constants import TUTOR_AGENT_NAME
from app.livekit.token import (
    generate_token,
    livekit_api_url,
    verify_token,
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET,
    LIVEKIT_HOST,
)
from app.auth.resolver import CurrentUser, get_current_user

router = APIRouter(prefix="/api/livekit", tags=["livekit"])


def _room_of(current_user: CurrentUser) -> str:
    """Salle déterministe de l'utilisateur — source de vérité unique.

    Utilisée par /token ( génération du JWT ), /agent/start ( dispatch )
    et /agent/stop|status. Toutes ces routes dérivent la salle de
    l'utilisateur authentifié : un client ne peut jamais cibler la
    salle d'un autre utilisateur.
    """
    return f"session_{current_user.user_id}"


class TokenRequest(BaseModel):
    """Requête pour obtenir un token LiveKit."""
    # room_name est accepté pour rétro-compatibilité mais IGNORE : la
    # salle est TOUJOURS calculée côté serveur ( voir _room_of ).
    # Un client qui choisit sa propre salle se retrouverait dans une
    # room différente de celle où l'agent est dispatché — l'agent
    # resterait muet, et la cause est invisible côté frontend.
    room_name: Optional[str] = None
    user_id: Optional[str] = None


class TokenResponse(BaseModel):
    """Réponse contenant le token et informations de connexion."""
    token: str
    url: str
    room_name: str


@router.post("/token", response_model=TokenResponse)
async def get_livekit_token(
    request: TokenRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Génère un token LiveKit pour rejoindre la room de l'utilisateur.

    Nécessite une authentification utilisateur valide.
    Le token est valable 60 minutes par défaut.

    La salle est calculée côté serveur ( session_{user_id} ) — c'est
    l'unique source de vérité, partagée avec /agent/start|stop|status.
    """
    # L'identité vient TOUJOURS du résolveur d'auth, jamais du client.
    user_id = current_user.user_id
    room_name = _room_of(current_user)

    try:
        token = generate_token(user_id=user_id, room_name=room_name)

        return TokenResponse(
            token=token,
            url=LIVEKIT_HOST,
            room_name=room_name
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate LiveKit token: {str(e)}"
        )


@router.post("/verify")
async def verify_livekit_token(
    token: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Vérifie la validité d'un token LiveKit.

    Utile pour valider un token côté serveur avant d'autoriser certaines
    actions. Authentification requise : un endpoint de vérification
    ouvert permettrait à quiconque de tester des tokens émis.
    """
    result = verify_token(token)

    if result is None or not result.get("valid"):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return {
        "valid": True,
        "identity": result.get("identity"),
        "grants": result.get("grants")
    }


# ------------------------------------------------------------------
# Agent temps réel — start / stop / status ( déclenchement frontend )
# ------------------------------------------------------------------


class AgentStartRequest(BaseModel):
    """Requête de démarrage de l'agent tuteur.

    thread_id est optionnel : si fourni, le transcript vocal est
    réinjecté dans ce thread en fin de session ( voir
    app.livekit.transcript ). Aucune validation de propriété ici —
    le thread_id voyage dans le metadata du dispatch et le worker le
    recroise avec l'identity du token, qui est forcée côté serveur.
    """

    thread_id: Optional[str] = None


# Jobs pas encore terminés : un dispatch dans cet état a déjà un
# worker qui tourne ( ou qui va le réclamer ), il ne faut pas en
# créer un second.
_LIVE_JOB_STATUSES = {JobStatus.JS_PENDING, JobStatus.JS_RUNNING}


@router.post("/agent/start")
async def start_agent(
    request: AgentStartRequest = AgentStartRequest(),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Démarre l'agent tuteur LiveKit dans la room de l'utilisateur.

    Crée la room si nécessaire puis y déploie l'agent ( AgentDispatch
    officiel LiveKit ). Si le serveur LiveKit n'est pas joignable
    ( ex : non démarré en local ), renvoie 503 plutôt qu'un 500 pour
    que le frontend puisse afficher un message clair.

    Idempotente : si un dispatch 'tutor' est déjà actif dans la room
    ( non supprimé et au moins un job PENDING/RUNNING ), on le RÉUTILISE
    au lieu d'en créer un nouveau. Sans cela, deux appels successifs
    ( ex : bouton voix + montage de la page /voice, ou StrictMode )
    déploient deux agents simultanés dans la même room.

    Le user_id de l'étudiant est injecté côté serveur dans le metadata
    du dispatch : le worker n'a pas de moyen sûr de le déduire lui-même
    ( ctx.local_participant_identity est l'identity du JOB agent ).
    """
    room_name = _room_of(current_user)

    # Le metadata du dispatch est la seule voie vers le worker :
    # user_id ( obligatoire pour la mémoire ) + thread_id ( optionnel ).
    payload: dict[str, Any] = {"user_id": str(current_user.user_id)}
    if request.thread_id:
        payload["thread_id"] = request.thread_id
    metadata = json.dumps(payload)

    try:
        async with LiveKitAPI(
            url=livekit_api_url(),
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET,
        ) as lkapi:
            # Idempotente : on réutilise un dispatch vivant s'il y en a un.
            dispatches = await lkapi.agent_dispatch.list_dispatch(room_name)
            for existing in dispatches:
                if existing.agent_name != TUTOR_AGENT_NAME:
                    continue
                if existing.state.deleted_at:
                    continue  # déjà supprimé — tombstone
                statuses = {job.state.status for job in existing.state.jobs}
                if statuses & _LIVE_JOB_STATUSES:
                    return {
                        "status": "started",
                        "room": room_name,
                        "agent": TUTOR_AGENT_NAME,
                        "dispatch_id": existing.id,
                        "reused": True,
                    }

            # Idempotente : retourne la room si elle existe déjà
            await lkapi.room.create_room(CreateRoomRequest(name=room_name))
            dispatch = await lkapi.agent_dispatch.create_dispatch(
                CreateAgentDispatchRequest(
                    room=room_name,
                    agent_name=TUTOR_AGENT_NAME,
                    metadata=metadata,
                )
            )
        return {
            "status": "started",
            "room": room_name,
            "agent": TUTOR_AGENT_NAME,
            "dispatch_id": dispatch.id,
            "reused": False,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Serveur LiveKit inaccessible — vérifiez que livekit-server "
                f"est démarré sur {livekit_api_url()} ({exc})"
            ),
        )


@router.get("/agent/status")
async def get_agent_status(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Retourne l'état de l'agent tuteur dans la room de l'utilisateur.

    Interroge LiveKit Cloud pour savoir si un dispatch 'tutor' est actif.
    Si la room n'existe pas ou n'a aucun dispatch → status = "stopped".
    Ne lève jamais d'erreur 503 : un agent absent est un état normal,
    pas une erreur.
    """
    room_name = _room_of(current_user)

    try:
        async with LiveKitAPI(
            url=livekit_api_url(),
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET,
        ) as lkapi:
            dispatches = await lkapi.agent_dispatch.list_dispatch(room_name)
            active = [d for d in dispatches if d.agent_name == TUTOR_AGENT_NAME]
            return {
                "status": "started" if active else "stopped",
                "room": room_name,
                "agent": TUTOR_AGENT_NAME,
                "dispatch_id": active[0].id if active else None,
                "active_count": len(active),
            }
    except Exception as exc:
        # LiveKit injoignable → on retourne "stopped" honnêtement,
        # sans obliger le frontend à gérer une erreur (le status endpoint
        # est utilisé pour l'affichage UI, pas pour un contrôle critique).
        return {
            "status": "stopped",
            "room": room_name,
            "agent": TUTOR_AGENT_NAME,
            "error": str(exc),
        }


@router.post("/agent/stop")
async def stop_agent(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Arrête l'agent tuteur déployé dans la room de l'utilisateur.

    L'API LiveKit 1.x demande l'identifiant du dispatch à supprimer ;
    on liste donc les dispatchs de la room et on les supprime un à un
    ( stop sans start préalable = liste vide = rien à faire ).
    """
    room_name = _room_of(current_user)

    try:
        async with LiveKitAPI(
            url=livekit_api_url(),
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET,
        ) as lkapi:
            dispatches = await lkapi.agent_dispatch.list_dispatch(room_name)
            for d in dispatches:
                await lkapi.agent_dispatch.delete_dispatch(d.id, room_name)
        return {
            "status": "stopped",
            "room": room_name,
            "agent": TUTOR_AGENT_NAME,
            "removed": len(dispatches),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Serveur LiveKit inaccessible — vérifiez que livekit-server "
                f"est démarré sur {livekit_api_url()} ({exc})"
            ),
        )
