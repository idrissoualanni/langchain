"""
LiveKit API Endpoints

Endpoints pour la gestion des sessions LiveKit (voice/video).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.livekit.token import generate_token, verify_token, LIVEKIT_HOST
from app.auth.resolver import get_current_user

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
    current_user: dict = Depends(get_current_user)
):
    """
    Génère un token LiveKit pour rejoindre une room.
    
    Nécessite une authentification utilisateur valide.
    Le token est valable 60 minutes par défaut.
    """
    # Utiliser l'ID utilisateur Clerk ou générer un ID anonyme
    user_id = request.user_id or current_user.get("sub", f"anon_{id(current_user)}")
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
