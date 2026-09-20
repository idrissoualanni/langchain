"""
LiveKit Token Generator

Génère des JWT tokens pour l'authentification des clients LiveKit.
Les tokens permettent de rejoindre des rooms avec des permissions spécifiques.
"""

import os
from datetime import timedelta
from livekit.api import AccessToken, TokenVerifier, VideoGrants

# Configuration : source unique dans app.config ( LIVEKIT_* ).
# Ces noms restent ré-exportés ici car app.api.livekit les importe.
from app.config import (
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET,
    LIVEKIT_HOST,
)


def livekit_api_url() -> str:
    """URL HTTP de l'API LiveKit ( RoomService / AgentDispatch ).

    Le projet ne définit que LIVEKIT_WS_URL ( wss://… ) ; LiveKitAPI
    attend une URL http(s)://. On convertit le schéma ws→http,
    wss→https, en laissant LIVEKIT_URL explicite primer si présente.
    """
    explicit = os.getenv("LIVEKIT_URL", "").strip()
    if explicit:
        return explicit
    ws = LIVEKIT_HOST.strip()
    if ws.startswith("wss://"):
        return "https://" + ws[len("wss://"):]
    if ws.startswith("ws://"):
        return "http://" + ws[len("ws://"):]
    return ws


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
    
    # livekit-api >= 1.x : AccessToken est un builder (les kwargs
    # identity/ttl/grants du constructeur n'existent plus).
    token = (
        AccessToken(api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET)
        .with_identity(user_id)
        .with_ttl(timedelta(minutes=ttl_minutes))
        .with_grants(
            VideoGrants(
                room=room_name,
                can_publish=True,          # Peut publier audio/vidéo
                can_subscribe=True,        # Peut s'abonner aux flux des autres
                can_publish_data=True,     # Peut envoyer des données (chat, metadata)
                # Sources autorisées : micro + caméra + partage d'écran
                # (requises par la session vidéo du tuteur)
                can_publish_sources=[
                    "camera",
                    "microphone",
                    "screen_share",
                ],
            )
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
        # AccessToken.verify a été remplacé par TokenVerifier (livekit-api 1.x).
        verifier = TokenVerifier(api_key=LIVEKIT_API_KEY, api_secret=secret)
        claims = verifier.verify(token)
        return {
            "identity": claims.identity,
            "valid": True,
            "grants": claims.video,
        }
    except Exception as e:
        print(f"Token verification failed: {e}")
        return None
