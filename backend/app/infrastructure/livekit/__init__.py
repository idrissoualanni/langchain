# LiveKit Integration Module
"""LiveKit integration helpers (API-only now).

L'agent vocal ne vit plus ici : il est déployé sur LiveKit Cloud
(agent `tutor`, projet `live`) depuis le dossier `agent/`.
Ce paquet ne sert plus qu'a l'API : capture d'ecran et jetons.
"""

from app.infrastructure.livekit.browser import (
    ScreenShareCapturer,
    set_screen_sharing,
    screen_share_status,
)
from app.infrastructure.livekit.constants import TUTOR_AGENT_NAME
from app.infrastructure.livekit.token import (
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET,
    LIVEKIT_HOST,
    generate_token,
    livekit_api_url,
    verify_token,
)

__all__ = [
    "ScreenShareCapturer",
    "set_screen_sharing",
    "screen_share_status",
    "TUTOR_AGENT_NAME",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "LIVEKIT_HOST",
    "generate_token",
    "livekit_api_url",
    "verify_token",
]