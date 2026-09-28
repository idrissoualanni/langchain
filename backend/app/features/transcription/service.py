"""Service de transcription Deepgram.

Utilise Deepgram Nova-3 pour la transcription en temps réel.
"""

import asyncio
import logging
from typing import AsyncIterable

from deepgram import Deepgram
from deepgram.transcription import LiveOptions

from app.config import DEEPGRAM_API_KEY

logger = logging.getLogger("agent-tutor.transcription")


class TranscriptionService:
    """Service de transcription vocale via Deepgram."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or DEEPGRAM_API_KEY
        self._client: Deepgram | None = None

    def _get_client(self) -> Deepgram:
        """Client Deepgram lazy (created on first use)."""
        if self._client is None:
            if not self.api_key:
                raise ValueError(
                    "DEEPGRAM_API_KEY non configurée. "
                    "Définissez-la dans votre fichier .env"
                )
            self._client = Deepgram(self.api_key)
        return self._client

    async def transcribe_audio(
        self,
        audio_data: bytes,
        language: str = "fr-FR",
        model: str = "nova-3",
    ) -> dict:
        """Transcrit un chunk audio (bytes).

        Args:
            audio_data: Audio brut (16-bit PCM 16kHz mono recommandé)
            language: Code langue (défaut: fr-FR)
            model: Modèle Deepgram (défaut: nova-3)

        Returns:
            Dict avec text, language, confidence, words
        """
        client = self._get_client()

        response = await client.transcription.prerecorded(
            {
                "buffer": audio_data,
                "mimetype": "audio/raw",
            },
            {
                "language": language,
                "model": model,
                "punctuate": True,
                "profanity_filter": False,
                "utterances": False,
            },
        )

        result = response["results"]["channels"][0]
        return {
            "text": result["alternatives"][0].get("transcript", ""),
            "language": language,
            "confidence": result["alternatives"][0].get("confidence", 0.0),
            "words": result["alternatives"][0].get("words", []),
        }

    async def stream_transcribe(
        self,
        audio_stream: AsyncIterable[bytes],
        language: str = "fr-FR",
        model: str = "nova-3",
    ) -> AsyncIterable[dict]:
        """Transcription en streaming via WebSocket Deepgram.

        Args:
            audio_stream: Flux asynchrone de chunks audio
            language: Code langue
            model: Modèle Deepgram

        Yields:
            Dict avec text, start, end, confidence pour chaque segment
        """
        client = self._get_client()

        async def audio_generator():
            """Générateur asynchrone pour Deepgram."""
            async for chunk in audio_stream:
                yield chunk

        try:
            connection = await client.transcription.live(
                {
                    "language": language,
                    "model": model,
                    "punctuate": True,
                    "profanity_filter": False,
                    "smart_format": True,
                    "interim_results": True,
                }
            )

            listener_task = None
            results_queue: asyncio.Queue[dict] = asyncio.Queue()

            async def on_message(_connection, result, **kwargs):
                await results_queue.put(result.to_dict())

            connection.on("transcript", on_message)

            async def send_audio():
                async for chunk in audio_stream:
                    connection.send(chunk)
                await connection.finish()

            listener_task = asyncio.create_task(send_audio())

            while True:
                try:
                    result = await asyncio.wait_for(
                        results_queue.get(), timeout=30.0
                    )
                except asyncio.TimeoutError:
                    break

                if result.get("is_final"):
                    yield {
                        "text": result["channel"]["alternatives"][0]["transcript"],
                        "start": result["words"][0]["start"]
                        if result.get("words") else 0,
                        "end": result["words"][-1]["end"]
                        if result.get("words") else 0,
                        "confidence": result["channel"]["alternatives"][0].get(
                            "confidence", 0.0
                        ),
                        "is_final": True,
                    }

        finally:
            if listener_task:
                listener_task.cancel()
                try:
                    await listener_task
                except asyncio.CancelledError:
                    pass


# Singleton
_transcription_service: TranscriptionService | None = None


def get_transcription_service() -> TranscriptionService:
    """Factory singleton pour le service de transcription."""
    global _transcription_service
    if _transcription_service is None:
        _transcription_service = TranscriptionService()
    return _transcription_service