"""API FastAPI pour la transcription STT.

Endpoints pour la transcription vocale standalone (découplée de LiveKit).
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from fastapi.responses import StreamingResponse
import asyncio
import logging

from app.features.transcription.schemas import (
    TranscriptionResponse,
    TranscriptionRequest,
)
from app.features.transcription.service import get_transcription_service
from app.auth.resolver import get_current_user

router = APIRouter(prefix="/api/transcription", tags=["transcription"])
logger = logging.getLogger("agent-tutor.transcription")


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(
    file: UploadFile = File(..., description="Fichier audio (WAV, PCM 16kHz mono)"),
    current_user=Depends(get_current_user),
):
    """Transcrit un fichier audio.

    Endpoint REST simple pour transcription de fichiers audio.
    Pour du streaming en temps réel, utiliser /transcribe/stream.
    """
    service = get_transcription_service()

    try:
        audio_data = await file.read()

        if len(audio_data) == 0:
            raise HTTPException(status_code=400, detail="Fichier audio vide")

        # Limite de taille: 10MB
        if len(audio_data) > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail="Fichier trop volumineux (max 10MB)"
            )

        result = await service.transcribe_audio(audio_data)

        return TranscriptionResponse(
            text=result["text"],
            language=result["language"],
            confidence=result["confidence"],
            words=result.get("words"),
        )

    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur transcription: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors de la transcription: {str(e)}"
        )


@router.post("/transcribe/stream")
async def transcribe_stream(
    request: TranscriptionRequest = TranscriptionRequest(),
    current_user=Depends(get_current_user),
):
    """Streaming de transcription via WebSocket.

    Le client envoie des chunks audio en streaming,
    le serveur retourne les transcriptions en temps réel.

    Note: Pour une implémentation complète WebSocket,
    utiliser un endpoint WebSocket dédié.
    """
    # Stream endpoint - à utiliser avec WebSocket client
    async def audio_generator():
        """Générateur factice - à remplacer par vrai flux WebSocket."""
        yield b""

    service = get_transcription_service()

    async def event_generator():
        async for result in service.stream_transcribe(
            audio_generator(),
            language=request.language,
            model=request.model,
        ):
            yield f"data: {result}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/status")
async def transcription_status(
    current_user=Depends(get_current_user),
):
    """Vérifie si le service de transcription est disponible."""
    service = get_transcription_service()
    try:
        # Test simple - essayer d'initialiser le client
        client = service._get_client()
        return {
            "status": "available",
            "provider": "deepgram",
            "model": "nova-3",
        }
    except ValueError as e:
        return {
            "status": "unavailable",
            "error": str(e),
        }