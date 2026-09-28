"""Serveur LiveKit — entrypoint du worker.

Ce module contient :
- AgentServer configuration
- Entry point RTC session (@server.rtc_session)
- Gestion du lifecycle (start, shutdown)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from livekit.agents import JobContext

from app.infrastructure.livekit.config import TUTOR_AGENT_NAME, get_agent_config
from app.infrastructure.livekit.errors import (
    CODE_JOB_SHUTDOWN,
    ErrorGuard,
    attach_error_handler,
    publish_error,
    spoken_message,
)
from app.infrastructure.livekit.memory_tools import (
    get_user_profile,
    get_user_memory,
    search_user_memory,
    save_user_memory,
)
from app.infrastructure.livekit.session import (
    build_session,
    build_instructions_async,
    resolve_user_id_from_job,
)
from app.infrastructure.livekit.browser import (
    ScreenShareCapturer,
    set_screen_sharing,
)
from app.infrastructure.livekit.transcript import (
    persist_transcript,
    thread_id_from_metadata,
)

logger = logging.getLogger("agent-tutor.livekit")


# ============================================================================
# CONFIGURATION SERVEUR
# ============================================================================

# Plan Render free : 512 Mi de RAM. Chaque processus idle est un
# interpréteur Python complet avec Silero VAD ( torch/onnxruntime )
# chargé en mémoire → ~200-300 Mi PAR processus. Avec 1 idle + le
# process principal on dépasse encore le plafond ( OOM ).
# num_idle_processes=0 : aucun agent préchargé — le worker en lance
# un à la demande quand un job arrive ( cold start de quelques
# secondes, acceptable pour un tuteur vocal ).
from livekit.agents import AgentServer

server = AgentServer(num_idle_processes=0)


# ============================================================================
# SESSION VOCALE
# ============================================================================

MEMORY_TOOLS = [
    get_user_profile,
    get_user_memory,
    search_user_memory,
    save_user_memory,
]


@server.rtc_session(agent_name=TUTOR_AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    """Point d'entrée appelé lorsqu'un dispatch pour `tutor`
    est attribué à ce worker.

    La gestion d'erreur LiveKit est entièrement déléguée à
    app.infrastructure.livekit.errors ( attach_error_handler + ErrorGuard ) :
    aucune panne Inference ne doit laisser l'étudiant face au silence.
    """
    # ------------------------------------------------------------------------
    # Résolution utilisateur
    # ------------------------------------------------------------------------

    metadata = getattr(ctx.job, "metadata", None)
    room_name = getattr(ctx.room, "name", None) or ""

    user_id = resolve_user_id_from_job(metadata, room_name)

    if not user_id:
        logger.error(
            "Impossible de résoudre user_id | metadata=%r | room=%s",
            getattr(ctx.job, "metadata", None),
            room_name,
        )
        publish_error(
            room_name=room_name,
            user_id="unknown",
            code="dispatch_misconfigured",
            recoverable=False,
            source="entrypoint",
            detail=(
                f"user_id irrésolvable depuis le dispatch "
                f"(metadata={metadata!r}) — agent stoppé immédiatement"
            ),
        )
        ctx.shutdown()
        return

    logger.info(
        "Dispatch tutor réclamé | room=%s | user=%s",
        room_name,
        user_id,
    )

    # ------------------------------------------------------------------------
    # Connexion à la room
    # ------------------------------------------------------------------------
    try:
        await ctx.connect()
    except Exception as exc:  # noqa: BLE001 — RTC fatal : rien à sauver
        from app.infrastructure.livekit.errors import classify_exception

        code, _ = classify_exception(exc)
        publish_error(
            room_name=room_name,
            user_id=user_id,
            code=code,
            recoverable=False,
            source="rtc",
            detail=f"ctx.connect() a échoué : {type(exc).__name__}: {exc}",
        )
        raise

    # ------------------------------------------------------------------------
    # Session vocale — une erreur de CONFIGURATION ( modèle absent du
    # catalogue, credentials Inference manquants ) est FATALE ici : on la
    # publie avec un code actionnable plutôt que de laisser un agent muet
    # en salle ( le piège historique de production ).
    # ------------------------------------------------------------------------
    from app.infrastructure.livekit.session import PipelineBuildError

    try:
        session = build_session()
    except PipelineBuildError as exc:
        publish_error(
            room_name=room_name,
            user_id=user_id,
            code="inference_invalid_model",
            recoverable=False,
            source="pipeline",
            detail=str(exc),
        )
        ctx.shutdown()
        return

    instructions = await build_instructions_async(user_id)

    from app.infrastructure.livekit.agent import TutorAgent

    tutor = TutorAgent(instructions=instructions)

    # ------------------------------------------------------------------------
    # Gestion d'erreurs LiveKit — ATTACHÉE AVANT session.start() : les
    # events "error"/"close" peuvent être émis dès les premières millisecondes
    # ( ex : premier token STT refusé ). Un par job, garde fraîche.
    # ------------------------------------------------------------------------
    guard = ErrorGuard()

    async def _on_fatal(code: str) -> None:
        """Arrêt propre ordonné par la garde anti-boucle."""
        publish_error(
            room_name=room_name,
            user_id=user_id,
            code=code,
            recoverable=False,
            source="guard",
            detail="seuil d'erreurs atteint — shutdown du job",
        )
        try:
            # Annonce vocale in-extremis : la session n'est pas encore
            # fermée quand "error" arrive avant la fermeture lib.
            await session.say(spoken_message(code), allow_interruptions=False)
        except Exception:  # noqa: BLE001 — muet vaut mieux qu'un crash ici
            pass
        ctx.shutdown(reason=f"livekit error: {code}")

    attach_error_handler(
        session,
        guard=guard,
        room=ctx.room,
        room_name=room_name,
        user_id=user_id,
        on_fatal=_on_fatal,
    )

    # ------------------------------------------------------------------------
    # Démarrage session
    # ------------------------------------------------------------------------
    # video_enabled=True : RoomIO s'abonne à la piste ScreenShare de
    # l'utilisateur. Sans ça, session.input.video reste None et le
    # ScreenShareCapturer n'a rien à consommer.
    from livekit.agents import room_io

    await session.start(
        agent=tutor,
        room=ctx.room,
        room_input_options=room_io.RoomInputOptions(video_enabled=True),
    )

    # ------------------------------------------------------------------------
    # Capture d'écran — l'agent "voit" l'écran partagé.
    # Non critique : un échec ici ne doit JAMAIS tuer la session vocale
    # ( on loggue + publie, et on continue sans vision ).
    # ------------------------------------------------------------------------
    try:
        capturer = ScreenShareCapturer()
        await capturer.attach(session)

        try:
            set_screen_sharing(ctx.room.name, capturer.is_sharing)
        except Exception as exc:
            logger.debug("état capture non remonté (%s)", exc)

        async def _on_capture_end() -> None:
            try:
                set_screen_sharing(ctx.room.name, False)
                capturer.detach()
            except Exception:
                pass

        ctx.add_shutdown_callback(_on_capture_end)
    except Exception as exc:  # noqa: BLE001 — la voix prime sur la vision
        capturer = None  # type: ignore[assignment]

        async def _on_capture_end() -> None:  # no-op, capture absente
            return

        publish_error(
            room_name=room_name,
            user_id=user_id,
            code="screen_capture_unavailable",
            recoverable=True,
            source="capturer",
            detail=f"capture écran désactivée pour ce job : {type(exc).__name__}: {exc}",
        )

    # ------------------------------------------------------------------------
    # Transcript
    # ------------------------------------------------------------------------
    thread_id = thread_id_from_metadata(
        getattr(ctx.job, "metadata", None)
    )

    async def _on_shutdown(reason: str) -> None:
        if not thread_id:
            logger.debug("Aucun thread_id : transcript non persisté.")
            return

        try:
            history = session.history
            await persist_transcript(
                user_id,
                thread_id,
                list(history.messages),
            )
            logger.info(
                "Transcript sauvegardé | user=%s | thread=%s",
                user_id,
                thread_id,
            )
        except Exception as exc:
            logger.warning(
                "Impossible de sauvegarder le transcript : %s",
                exc,
            )

    ctx.add_shutdown_callback(_on_shutdown)
    ctx.add_shutdown_callback(_on_capture_end)