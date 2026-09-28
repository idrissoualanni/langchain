"""Construction de la session vocale LiveKit.

Découplée de l'agent principal pour faciliter les tests et la reconfiguration.
"""

from __future__ import annotations

import asyncio
from typing import Any

from livekit.agents import (
    AgentSession,
    TurnHandlingOptions,
    inference,
    llm,
    room_io,
)
from livekit.plugins import silero

from app.infrastructure.livekit.config import AgentConfig, get_agent_config


def build_session(
    config: AgentConfig | None = None,
) -> AgentSession:
    """Construit la chaîne vocale : STT → LLM → TTS.

    Args:
        config: Configuration de l'agent (utilise les variables d'env par défaut)

    Returns:
        AgentSession configuré avec STT/LLM/TTS/VAD
    """
    if config is None:
        config = get_agent_config()

    tts_kwargs: dict[str, Any] = {
        "model": config.tts_model,
        "language": config.language,
    }

    # La voix est optionnelle
    if config.tts_voice:
        tts_kwargs["voice"] = config.tts_voice

    return AgentSession(
        # STT
        stt=inference.STT(
            model=config.stt_model,
            language=config.language,
        ),

        # LLM
        llm=inference.LLM(
            model=config.llm_model,
        ),

        # TTS
        tts=inference.TTS(
            **tts_kwargs,
        ),

        # VAD
        vad=silero.VAD.load(),

        # Gestion des tours de parole
        turn_handling=TurnHandlingOptions(
            turn_detection=inference.TurnDetector(),
            preemptive_generation={
                "enabled": config.preemptive_generation,
            },
        ),

        # Limite de tool calls
        max_tool_steps=config.max_tool_steps,
    )


# ============================================================================
# CONTEXTE UTILISATEUR
# ============================================================================

# Compte de test isolé pour les rooms créées par la Console LiveKit
_CONSOLE_TEST_USER_ID = "livekit-console-test"


def resolve_user_id_from_job(
    metadata: str | None,
    room_name: str | None,
) -> str | None:
    """Résout l'identité persistante de l'étudiant depuis le job LiveKit.

    Priorité :
    1. metadata du dispatch ( JSON contenant user_id )
    2. nom de room session_<user_id>
    3. room console-xxxxxxxx ou "test" → compte de test isolé
    4. sinon None

    Args:
        metadata: JSON metadata du dispatch LiveKit
        room_name: Nom de la room LiveKit

    Returns:
        user_id ou None si non résolu
    """
    import json

    # 1. Metadata JSON
    if isinstance(metadata, str) and metadata.strip():
        try:
            payload = json.loads(metadata)
            if isinstance(payload, dict):
                user_id = payload.get("user_id")
                if isinstance(user_id, str) and user_id.strip():
                    return user_id.strip()
        except json.JSONDecodeError:
            pass

    # 2. Fallback sur le nom de room
    if room_name and room_name.startswith("session_"):
        candidate = room_name[len("session_") :]
        if candidate:
            return candidate

    # 3. Rooms de test
    if room_name and (room_name.startswith("console-") or room_name == "test"):
        return _CONSOLE_TEST_USER_ID

    return None


async def build_instructions_async(
    user_id: str,
) -> str:
    """Construit les instructions : lectures mémoire hors de la loop.

    Les deux appels SQL synchrones sont dispatchés vers l'executor au
    lieu de bloquer la boucle asyncio.
    """
    from app.services.memory.memory import (
        memory_overview_for_api,
        read_profile,
    )

    def _read_profile_safe(uid: str) -> dict:
        try:
            return read_profile(uid)
        except Exception:
            return {}

    def _memory_overview_safe(uid: str) -> dict:
        try:
            return memory_overview_for_api(uid)
        except Exception:
            return {}

    from app.infrastructure.livekit.config import build_system_instructions

    loop = asyncio.get_running_loop()
    profile, overview = await asyncio.gather(
        loop.run_in_executor(None, _read_profile_safe, user_id),
        loop.run_in_executor(None, _memory_overview_safe, user_id),
    )
    return build_system_instructions(profile, overview)