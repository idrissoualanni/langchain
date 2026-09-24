"""
Capture d'écran du navigateur de l'utilisateur — worker LiveKit.

L'agent tuteur peut "voir" ce que l'étudiant partage : ce module échantillonne
la piste vidéo ScreenShare reçue via RoomIO ( video_enabled=True ) et maintient
le DERNIER frame disponible. L'agent le lit à la demande ( ex: l'étudiant pose
une question sur ce qui est affiché ) et l'injecte dans son ChatContext sous
forme d'ImageContent — le LLM multimodal le voit alors comme une image.

Pourquoi un module dédié :
    - push_video() de la base DuplexModel est un no-op ( ignoré par les modèles
      non-realtime comme inference.LLM ). Il faut consommer self.input.video
      soi-même.
    - Le frame est décodé/converti UNE fois ici, pas à chaque question.

Consommation :
    capturer = ScreenShareCapturer()
    await capturer.attach(session)
    frame = capturer.latest        # rtc.VideoFrame | None
    capturer.detach()

Non-fatal : aucune erreur de capture ne doit casser la session vocale.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from livekit import rtc

logger = logging.getLogger("agent-tutor.livekit")


# Registre partagé backend ↔ worker : pour chaque room, l'état de capture
# ( un frame est-il disponible ? ). Le worker écrit, l'API lit
# ( GET /screen-share/status ). browser n'importe rien de app.api — pas de
# dépendance circulaire, le worker peut l'importer librement.
_screen_share_registry: dict[str, dict[str, Any]] = {}


def set_screen_sharing(room_name: str, enabled: bool) -> None:
    """Met à jour l'état de capture pour une room — appelé par le worker."""
    if enabled:
        _screen_share_registry[room_name] = {
            "capturing": True,
            "started_at": int(time.time()),
        }
    else:
        _screen_share_registry.pop(room_name, None)


def screen_share_status(room_name: str) -> dict[str, Any] | None:
    """État de capture pour une room — lu par l'API."""
    return _screen_share_registry.get(room_name)

logger = logging.getLogger("agent-tutor.livekit")


class ScreenShareCapturer:
    """Maintient le dernier frame vidéo de l'écran partagé par l'utilisateur.

    La piste ScreenShare arrive via session.input.video ( un AsyncIterable de
    rtc.VideoFrame ) dès que video_enabled=True dans RoomInputOptions. On ne
    garde que le frame le plus récent : la vision agent est ponctuelle
    ( "regarde mon écran" ), pas un flux vidéo continu.
    """

    def __init__(self, max_fps: float = 2.0) -> None:
        self._latest: rtc.VideoFrame | None = None
        self._task: asyncio.Task[None] | None = None
        # Échantillonnage : on ne garde pas 30 frames/s ( inutile pour du
        # questionnement ponctuel, coûteux en CPU ). 2 fps suffisent pour
        # que l'image soit fraîche quand l'agent la demande.
        self._min_interval = 1.0 / max_fps if max_fps > 0 else 0.0
        self._last_capture = 0.0

    @property
    def latest(self) -> rtc.VideoFrame | None:
        """Dernier frame disponible, ou None si rien n'est partagé."""
        return self._latest

    @property
    def is_sharing(self) -> bool:
        return self._latest is not None

    async def attach(self, session: Any) -> None:
        """Branche le capturer sur l'entrée vidéo de la session.

        session.input.video est None si video_enabled n'est pas actif —
        dans ce cas on log et on reste inerte ( pas d'erreur ).
        """
        video_input = getattr(getattr(session, "input", None), "video", None)
        if video_input is None:
            logger.info("capture écran inactive — video non activé sur la session")
            return

        if self._task is not None:
            return  # déjà attaché

        self._task = asyncio.create_task(self._consume(video_input))
        logger.info("capture écran démarrée | source=%s", type(video_input).__name__)

    async def _consume(self, video_input: Any) -> None:
        """Boucle de consommation : garde uniquement le dernier frame."""
        try:
            async for frame in video_input:
                loop = asyncio.get_running_loop()
                now = loop.time()
                if self._min_interval and (now - self._last_capture) < self._min_interval:
                    continue
                self._last_capture = now
                self._latest = frame
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — la capture ne doit jamais casser la voix
            logger.warning("capture écran interrompue (%s)", exc)
        finally:
            self._latest = None

    def detach(self) -> None:
        """Détache proprement ( session fermée )."""
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self._latest = None
