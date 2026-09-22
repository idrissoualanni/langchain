# SHIM de compatibilité (refactor — phase migration).
#
# LiveKit a déménagé vers app/infrastructure/livekit/.
# SUPPRESSION prévue phase cleanup (§30 mission) après vérification.
from app.infrastructure.livekit import (
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET,
    LIVEKIT_HOST,
    ScreenShareCapturer,
    TUTOR_AGENT_NAME,
    generate_token,
    livekit_api_url,
    persist_transcript,
    thread_id_from_metadata,
    verify_token,
)

__all__ = [
    "ScreenShareCapturer",
    "TUTOR_AGENT_NAME",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "LIVEKIT_HOST",
    "generate_token",
    "livekit_api_url",
    "verify_token",
    "persist_transcript",
    "thread_id_from_metadata",
]
