"""
LiveKit API Endpoints

Endpoints pour la gestion des sessions LiveKit (voice/video).
"""

from fastapi import APIRouter, Depends, HTTPException
from livekit.api import (
    CreateAgentDispatchRequest,
    CreateRoomRequest,
    DeleteAgentDispatchRequest,
    LiveKitAPI,
)
from pydantic import BaseModel
from typing import Optional

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


class TokenRequest(BaseModel):
    """Requête pour obtenir un token LiveKit."""
    room_name: Optional[str] = "tutor-session"
    user_id: Optional[str] = None


class TokenResponse(BaseModel):
    """Réponse contenant le token et les informations de connexion."""
    token: str
    url: str
    room_name: str


@router.post("/token", response_model=TokenResponse)
async def get_livekit_token(
    request: TokenRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Génère un token LiveKit pour rejoindre une room.

    Nécessite une authentification utilisateur valide.
    Le token est valable 60 minutes par défaut.
    """
    # L'identité vient TOUJOURS du résolveur d'auth, jamais du client.
    user_id = current_user.user_id
    room_name = request.room_name or f"session_{user_id}"
    
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
async def verify_livekit_token(token: str):
    """
    Vérifie la validité d'un token LiveKit.

    Utile pour valider un token côté serveur avant d'autoriser certaines actions.
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
# Agent temps réel — start / stop ( déclenchement frontend )
# ------------------------------------------------------------------

TUTOR_AGENT_NAME = "tutor"


def _room_of(current_user: CurrentUser) -> str:
    return f"session_{current_user.user_id}"


@router.post("/agent/start")
async def start_agent(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Démarre l'agent tuteur LiveKit dans la room de l'utilisateur.

    Crée la room si nécessaire puis y déploie l'agent ( AgentDispatch
    officiel LiveKit ). Si le serveur LiveKit n'est pas joignable
    ( ex : non démarré en local ), renvoie 503 plutôt qu'un 500 pour
    que le frontend puisse afficher un message clair.
    """
    room_name = _room_of(current_user)

    try:
        async with LiveKitAPI(
            url=livekit_api_url(),
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET,
        ) as lkapi:
            # Idempotente : retourne la room si elle existe déjà
            await lkapi.room.create_room(CreateRoomRequest(name=room_name))
            dispatch = await lkapi.agent_dispatch.create_dispatch(
                CreateAgentDispatchRequest(
                    room=room_name,
                    agent_name=TUTOR_AGENT_NAME,
                )
            )
        return {
            "status": "started",
            "room": room_name,
            "agent": TUTOR_AGENT_NAME,
            "dispatch_id": dispatch.id,
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


@router.post("/agent/stop")
async def stop_agent(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Arrête l'agent tuteur déployé dans la room de l'utilisateur."""
    room_name = _room_of(current_user)

    try:
        async with LiveKitAPI(
            url=livekit_api_url(),
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET,
        ) as lkapi:
            await lkapi.agent_dispatch.delete_dispatch(
                DeleteAgentDispatchRequest(room=room_name)
            )
        return {
            "status": "stopped",
            "room": room_name,
            "agent": TUTOR_AGENT_NAME,
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
