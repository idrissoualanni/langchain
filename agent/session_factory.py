"""Construction de la session vocale LiveKit (STT → LLM → TTS).

Portage de `backend/app/infrastructure/livekit/session.py` pour un agent
autonome : la validation du catalogue LiveKit Inference est CONSERVÉE, car
c'est elle qui transforme un modèle mal configuré en échec de démarrage
visible dans les logs, au lieu d'un agent muet en salle.
"""

from __future__ import annotations

import json
import logging
import os
import typing
from typing import Any

from livekit.agents import AgentSession, TurnHandlingOptions, inference
from livekit.plugins import silero

from config import AgentConfig, get_agent_config

logger = logging.getLogger("agent-tutor.livekit.session")


class PipelineBuildError(RuntimeError):
    """Échec de construction du pipeline vocal (configuration fatale).

    Levée AVANT ctx.connect() : l'agent ne rejoint jamais une room pour y
    rester muet, le job s'arrête avec un message explicite dans les logs.
    """


#: Replis vérifiés dans le catalogue Inference (identifiants jamais inventés).
_LLM_FALLBACKS = ["google/gemini-2.5-flash", "openai/gpt-4o-mini"]
_STT_FALLBACKS = ["deepgram/nova-3", "deepgram/nova-2", "assemblyai/universal-streaming-multilingual"]
_TTS_FALLBACKS = ["rime/coda", "cartesia/sonic-3", "deepgram/aura-2"]


def _known_models(enum_name: str) -> set[str]:
    """Modèles valides du catalogue Inference (STTModels/LLMModels/TTSModels).

    Ce sont des alias `typing` (Union de Literal), pas des enums. Échec
    d'introspection → ensemble vide, et `_validate_model` laisse alors
    tout passer (ne jamais bloquer un déploiement sur un détail d'API).
    """
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
    """Vérifie le modèle contre le catalogue ; bascule sur un repli valide."""
    known = _known_models(f"{kind}Models")
    if not known:
        return model
    for candidate in [model, *fallbacks]:
        # Les entrées du catalogue peuvent porter un suffixe ":langue".
        base = candidate.split(":")[0]
        if base in known or candidate in known:
            if candidate != model:
                logger.error(
                    "Modèle %s '%s' ABSENT du catalogue LiveKit Inference — "
                    "repli automatique sur '%s'. Corrige LIVEKIT_%s_MODEL.",
                    kind.lower(), model, candidate, kind.upper(),
                )
            return candidate
    raise PipelineBuildError(
        f"Modèle {kind.lower()} '{model}' absent du catalogue LiveKit Inference "
        f"et aucun repli disponible parmi {fallbacks}. "
        f"Choisis un modèle valide (ex : {fallbacks[0]})."
    )


def build_session(config: AgentConfig | None = None) -> AgentSession:
    """Construit la chaîne vocale : STT → LLM → TTS (+ VAD)."""
    if config is None:
        config = get_agent_config()

    # Credentials Inference : inference.* les lit dans l'environnement et
    # lève un ValueError opaque ("api_key is required") si absents.
    if not os.getenv("LIVEKIT_API_KEY") or not os.getenv("LIVEKIT_API_SECRET"):
        raise PipelineBuildError(
            "LIVEKIT_API_KEY / LIVEKIT_API_SECRET absents de l'environnement "
            "de l'agent — le pipeline Inference ne peut pas s'authentifier."
        )

    stt_model = _validate_model("STT", config.stt_model, _STT_FALLBACKS)
    llm_model = _validate_model("LLM", config.llm_model, _LLM_FALLBACKS)
    tts_model = _validate_model("TTS", config.tts_model, _TTS_FALLBACKS)

    tts_kwargs: dict[str, Any] = {"model": tts_model, "language": config.language}
    if config.tts_voice:
        tts_kwargs["voice"] = config.tts_voice

    try:
        session = AgentSession(
            stt=inference.STT(
                model=stt_model,
                language=config.language,
                fallback=_STT_FALLBACKS[1:],
            ),
            llm=inference.LLM(
                model=llm_model,
            ),
            tts=inference.TTS(**tts_kwargs),
            vad=silero.VAD.load(),
            turn_handling=TurnHandlingOptions(
                turn_detection=inference.TurnDetector(),
                preemptive_generation={"enabled": config.preemptive_generation},
            ),
            max_tool_steps=config.max_tool_steps,
        )
    except ValueError as exc:
        # Les ValueError d'inference.* sont des erreurs de CONFIGURATION
        # (clé API, modèle, langue) — jamais transitoires.
        raise PipelineBuildError(f"Pipeline vocal invalide : {exc}") from exc

    return session


# ============================================================================
# CONTEXTE UTILISATEUR
# ============================================================================

#: Compte de test isolé pour les rooms créées par la console LiveKit.
_CONSOLE_TEST_USER_ID = "livekit-console-test"


def resolve_user_id_from_job(
    metadata: str | None,
    room_name: str | None,
) -> str | None:
    """Résout l'identité persistante de l'étudiant depuis le job LiveKit.

    Priorité : metadata du dispatch (JSON `user_id`) → nom de room
    `session_<user_id>` → room de test console → None.
    """
    if isinstance(metadata, str) and metadata.strip():
        try:
            payload = json.loads(metadata)
            if isinstance(payload, dict):
                user_id = payload.get("user_id")
                if isinstance(user_id, str) and user_id.strip():
                    return user_id.strip()
        except json.JSONDecodeError:
            pass

    if room_name and room_name.startswith("session_"):
        candidate = room_name[len("session_"):]
        if candidate:
            return candidate

    if room_name and (room_name.startswith("console-") or room_name == "test"):
        return _CONSOLE_TEST_USER_ID

    return None
