# LiveKit Integration Module
"""
LiveKit Agents integration for realtime voice/video sessions.
"""
# Façade du sous-package livekit (refactor — couche infrastructure).
#
# Ré-exporte l'API publique légère (constantes, tokens, transcript,
# capture écran). Le worker vocal (agent) reste importé depuis son
# sous-module dédié (app.infrastructure.livekit.agent) car il porte
# des dépendances lourdes (livekit-agents, silero) et des effets de
# bord à l'import (AgentServer).
from app.infrastructure.livekit.browser import ScreenShareCapturer
from app.infrastructure.livekit.constants import TUTOR_AGENT_NAME
from app.infrastructure.livekit.token import (
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET,
    LIVEKIT_HOST,
    generate_token,
    livekit_api_url,
    verify_token,
)
from app.infrastructure.livekit.transcript import (
    persist_transcript,
    thread_id_from_metadata,
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
