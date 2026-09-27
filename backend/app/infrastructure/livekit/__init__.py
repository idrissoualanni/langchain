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
from app.infrastructure.livekit.transcript import (
    persist_transcript,
    thread_id_from_metadata,
)
from app.infrastructure.livekit.config import (
    AgentConfig,
    get_agent_config,
    BASE_INSTRUCTIONS,
    build_system_instructions,
    TUTOR_AGENT_NAME as _AGENT_NAME,
)
from app.infrastructure.livekit.session import (
    build_session,
    resolve_user_id_from_job,
    build_instructions_async,
)
from app.infrastructure.livekit.agent import TutorAgent
from app.infrastructure.livekit.server import server

__all__ = [
    # Browser/Screen
    "ScreenShareCapturer",
    "set_screen_sharing",
    "screen_share_status",
    # Constants
    "TUTOR_AGENT_NAME",
    # Token
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "LIVEKIT_HOST",
    "generate_token",
    "livekit_api_url",
    "verify_token",
    # Transcript
    "persist_transcript",
    "thread_id_from_metadata",
    # Config
    "AgentConfig",
    "get_agent_config",
    "BASE_INSTRUCTIONS",
    "build_system_instructions",
    # Session
    "build_session",
    "resolve_user_id_from_job",
    "build_instructions_async",
    # Agent
    "TutorAgent",
    # Server
    "server",
]