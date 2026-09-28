"""Module transcription STT — Deepgram.

Découple la fonctionnalité de transcription vocale de l'agent LiveKit.
Permet une utilisation standalone (dictée, reconnaissance vocale).
"""

from app.features.transcription.service import TranscriptionService
from app.features.transcription.api import router as transcription_router

__all__ = ["TranscriptionService", "transcription_router"]