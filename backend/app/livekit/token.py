"""
LiveKit Token Generator

Génère des JWT tokens pour l'authentification des clients LiveKit.
Les tokens permettent de rejoindre des rooms avec des permissions spécifiques.
"""

import os
from datetime import timedelta
from livekit.api import AccessToken, VideoGrants

# Configuration depuis les variables d'environnement
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "devsecret")
LIVEKIT_HOST = os.getenv("LIVEKIT_WS_URL", "wss://localhost:7880")


def generate_token(
    user_id: str, 
    room_name: str, 
    ttl_minutes: int = 60
) -> str:
    """
    Génère un token JWT pour rejoindre une room LiveKit.
    
    Args:
        user_id: Identifiant unique de l'utilisateur (utilisé comme identity)
        room_name: Nom de la room à rejoindre
        ttl_minutes: Durée de validité du token en minutes (défaut: 60)
    
    Returns:
        str: Token JWT encodé
    
    Raises:
        ValueError: Si les clés API ne sont pas configurées
    """
    if LIVEKIT_API_KEY == "devkey" or LIVEKIT_API_SECRET == "devsecret":
        # Mode développement - warning dans les logs
        print("⚠️  WARNING: Using default LiveKit credentials. Set LIVEKIT_API_KEY and LIVEKIT_API_SECRET in .env")
    
    token = AccessToken(
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
        identity=user_id,
        ttl=timedelta(minutes=ttl_minutes),
        grants=VideoGrants(
            room=room_name,
            can_publish=True,          # Peut publier audio/vidéo
            can_subscribe=True,        # Peut s'abonner aux flux des autres
            can_publish_data=True,     # Peut envoyer des données (chat, metadata)
            can_publish_sources=["microphone"],  # Sources autorisées
        )
    )
    
    return token.to_jwt()


def verify_token(token: str, api_secret: str | None = None) -> dict | None:
    """
    Vérifie et décode un token LiveKit.
    
    Args:
        token: Le token JWT à vérifier
        api_secret: Secret API pour vérification (défaut: LIVEKIT_API_SECRET)
    
    Returns:
        dict: Informations du token (identity, grants, etc.) ou None si invalide
    """
    secret = api_secret or LIVEKIT_API_SECRET
    try:
        decoded = AccessToken.verify(token, secret)
        return {
            "identity": decoded.identity,
            "valid": True,
            "grants": decoded.grants
        }
    except Exception as e:
        print(f"Token verification failed: {e}")
        return None
