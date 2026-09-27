"""Schémas Pydantic pour la transcription STT."""

from pydantic import BaseModel
from typing import Optional


class TranscriptionRequest(BaseModel):
    """Requête de transcription (optionnel - streaming preferido)."""
    language: str = "fr-FR"
    profanity_filter: bool = False
    punctuate: bool = True
    model: str = "nova-3"


class TranscriptionResponse(BaseModel):
    """Réponse de transcription."""
    text: str
    language: str
    confidence: float
    words: Optional[list[dict]] = None


class TranscriptionSegment(BaseModel):
    """Segment de transcription avec timing."""
    text: str
    start: float
    end: float
    confidence: float
    speaker: Optional[int] = None