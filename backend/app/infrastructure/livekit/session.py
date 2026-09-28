"""Construction de la session vocale LiveKit.

Découplée de l'agent principal pour faciliter les tests et la reconfiguration.
Toute la logique d'erreur du pipeline ( classification, garde anti-boucle,
handlers ) vit dans app.infrastructure.livekit.errors — ce module se
contente de lever PipelineBuildError ( erreur de CONFIGURATION fatale ).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from livekit.agents import (
    AgentSession,
    TurnHandlingOptions,
    inference,
)
from livekit.plugins import silero

from app.infrastructure.livekit.config import AgentConfig, get_agent_config

logger = logging.getLogger("agent-tutor.livekit.session")


class PipelineBuildError(RuntimeError):
    """Échec de construction du pipeline vocal ( config invalide ).

    Levée PAR build_session quand un modèle est refusé par le catalogue
    LiveKit Inference ou quand les credentials manquent. C'est une erreur
    FATALE : l'agent ne doit pas rejoindre la room pour y rester muet —
    l'entrypoint la convertit en log + shutdown immédiat.
    """


#: Modèles de repli si le modèle principal est absent du catalogue.
#: Uniquement des identifiants VÉRIFIÉS dans le catalogue 1.8.x
#: ( typing.get_args sur STTModels/LLMModels/TTSModels ) — jamais inventés.
_LLM_FALLBACKS = ["openai/gpt-4o-mini", "google/gemini-2.5-flash"]
_STT_FALLBACKS = ["deepgram/nova-3", "deepgram/nova-2", "assemblyai/universal-streaming-multilingual"]
_TTS_FALLBACKS = ["rime/coda", "cartesia/sonic-3", "deepgram/aura-2"]


def _known_models(enum_name: str) -> set[str]:
    """Modèles valides du catalogue Inference ( STTModels/LLMModels/TTSModels ).

    Ce sont des alias typing ( Union de Literal ), pas des enums : on
    extrait les valeurs via typing.get_args. Échec d'introspection →
    ensemble vide, et _validate_model laisse alors tout passer ( ne
    jamais bloquer un déploiement à cause d'un changement d'API interne ).
    """
    import typing

    try:
        alias = getattr(inference, enum_name)
        out: set[str] = set()
        for arg in typing.get_args(alias):
            inner = getattr(arg, "__args__", None)
            if inner:
                out.update(str(x) for x in inner)
            else:
                out.add(str(arg))
        return out
    except Exception:  # noqa: BLE001 — catalogue introuvable → on n'entrave pas
        return set()


def _validate_model(kind: str, model: str, fallbacks: list[str]) -> str:
    """Vérifie le modèle contre le catalogue ; bascule sur un repli valide.

    Le piège de production historique : un modèle inexistant ( ex :
    "google/gemma-4-31b-it" ) ne fait PAS échouer le worker — il lève au
    premier tour de parole, dans le job subprocess, hors des logs Render.
    En le détectant ICI ( avant ctx.connect() ), l'erreur devient visible
    dans les logs du service et le job s'arrête proprement.
    """
    known = _known_models(f"{kind}Models")
    if not known:
        return model  # pas de catalogue accessible → on laisse passer
    candidates = [model, *fallbacks]
    for candidate in candidates:
        # Les modèles du catalogue peuvent porter un suffixe ":langue"
        base = candidate.split(":")[0]
        if base in known or candidate in known:
            if candidate != model:
                logger.error(
                    "Modèle %s '%s' ABSENT du catalogue LiveKit Inference — "
                    "repli automatique sur '%s'. Corrige LIVEKIT_AGENT_%s_MODEL.",
                    kind.lower(), model, candidate, kind.upper(),
                )
            return candidate
    raise PipelineBuildError(
        f"Modèle {kind.lower()} '{model}' absent du catalogue LiveKit Inference "
        f"et aucun repli disponible parmi {fallbacks}. "
        f"Choisis un modèle valide ( ex : {fallbacks[0]} )."
    )


def build_session(
    config: AgentConfig | None = None,
) -> AgentSession:
    """Construit la chaîne vocale : STT → LLM → TTS.

    Chaque modèle est d'abord VALIDÉ contre le catalogue Inference
    ( voir _validate_model ) : mieux vaut un job qui refuse de démarrer
    avec un message explicite qu'un agent muet en salle.

    Args:
        config: Configuration de l'agent (utilise les variables d'env par défaut)

    Returns:
        AgentSession configuré avec STT/LLM/TTS/VAD

    Raises:
        PipelineBuildError: modèle inconnu sans repli possible, ou
            credentials Inference manquants ( LIVEKIT_API_KEY/SECRET ).
    """
    if config is None:
        config = get_agent_config()

    # Credentials Inference : inference.STT/LLM/TTS lisent LIVEKIT_API_KEY
    # /LIVEKIT_API_SECRET depuis l'environnement ET lèvent un ValueError
    # obscure ("api_key is required") si absents. On vérifie avant pour
    # produire un message actionnable dans les logs Render.
    import os

    if not os.getenv("LIVEKIT_API_KEY") or not os.getenv("LIVEKIT_API_SECRET"):
        raise PipelineBuildError(
            "LIVEKIT_API_KEY / LIVEKIT_API_SECRET absents de l'environnement "
            "du worker — le pipeline Inference ne peut pas s'authentifier."
        )

    stt_model = _validate_model("STT", config.stt_model, _STT_FALLBACKS)
    llm_model = _validate_model("LLM", config.llm_model, _LLM_FALLBACKS)
    tts_model = _validate_model("TTS", config.tts_model, _TTS_FALLBACKS)

    tts_kwargs: dict[str, Any] = {
        "model": tts_model,
        "language": config.language,
    }

    # La voix est optionnelle
    if config.tts_voice:
        tts_kwargs["voice"] = config.tts_voice

    try:
        session = AgentSession(
            # STT (+ repli automatique si le fournisseur principal 5xx )
            stt=inference.STT(
                model=stt_model,
                language=config.language,
                fallback=_STT_FALLBACKS[1:],
            ),

            # LLM
            llm=inference.LLM(
                model=llm_model,
                fallback=[m for m in _LLM_FALLBACKS if m != llm_model],
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
    except ValueError as exc:
        # Les ValueError d'inference.* sont des erreurs de CONFIGURATION
        # ( clé API, modèle, langue ) — jamais transitoires.
        raise PipelineBuildError(f"Pipeline vocal invalide : {exc}") from exc

    return session


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