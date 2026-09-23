# VideoSubgraph — TRANSCRIPTION RÉELLE via faster-whisper.
#
# Remplace le bouchon déterministe (_default_transcriber dans ingest.py)
# par une vraie reconnaissance vocale offline (faster-whisper, CPU). Le
# modèle se télécharge une fois (HF Hub) puis tourne localement — aucun
# secret, aucune requête permanente.
#
# Politique d'activation (config VIDEO_TRANSCRIPTION_MODE) :
#   auto    → whisper si la lib est installée, sinon bouchon ;
#   whisper → whisper forcé (VideoFatalError si lib absente) ;
#   offline → bouchon forcé (tests, hors-ligne).
#
# En cas d'échec de transcription (audio absent/incompréhensible), on
# lève VideoFatalError : le subgraph doit signaler l'échec plutôt que
# de servir un transcript de complaisance (mission : JAMAIS de contenu
# fabriqué présenté comme analysé).
from __future__ import annotations

from app.config import (
    VIDEO_TRANSCRIPTION_MODE,
    VIDEO_WHISPER_COMPUTE,
    VIDEO_WHISPER_DEVICE,
    VIDEO_WHISPER_LANGUAGE,
    VIDEO_WHISPER_MODEL,
)
from app.logging.events import log_event

# Modèle chargé une fois (téléchargement HF au premier appel).
_whisper_model = None


def _whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False


def _get_whisper_model():
    """Instance WhisperModel (lazy, singleton module)."""
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        log_event(
            "VIDEO_WHISPER_INIT",
            message=(
                f"Loading whisper model | model={VIDEO_WHISPER_MODEL} "
                f"| device={VIDEO_WHISPER_DEVICE}"
            ),
            extra={
                "operation": "video_transcribe",
                "model": VIDEO_WHISPER_MODEL,
                "device": VIDEO_WHISPER_DEVICE,
            },
        )
        _whisper_model = WhisperModel(
            VIDEO_WHISPER_MODEL,
            device=VIDEO_WHISPER_DEVICE,
            compute_type=VIDEO_WHISPER_COMPUTE,
        )
    return _whisper_model


def whisper_transcriber(
    local_path: str = "",
    audio_path: str = "",
    filename: str = "",
    duration: float = 0.0,
) -> str:
    """Transcriber RÉEL — signature compatible de l'interface injectable.

    faster-whisper décode lui-même l'audio du média (ffmpeg/libav), y
    compris depuis un conteneur vidéo MP4. Lève VideoFatalError si
    l'audio est absent ou inaudible (jamais de texte de complaisance).
    """
    from app.graph.subgraphs.video.ingest import VideoFatalError

    try:
        model = _get_whisper_model()
        segments, info = model.transcribe(
            local_path or audio_path,
            language=(VIDEO_WHISPER_LANGUAGE or None),
            beam_size=5,
            vad_filter=True,
        )
        text = " ".join(
            str(seg.text).strip() for seg in (segments or [])
        ).strip()
    except Exception as exc:
        # Erreur de décodage (audio absent, format illisible) → fatal.
        log_event(
            "VIDEO_WHISPER_ERROR",
            level="ERROR",
            message=f"Transcription failed: {type(exc).__name__}",
            extra={
                "operation": "video_transcribe",
                "error": str(exc)[:300],
                "filename": filename,
            },
        )
        raise VideoFatalError(
            f"transcription impossible ({type(exc).__name__}: {exc})"
        ) from exc

    if not text:
        log_event(
            "VIDEO_WHISPER_EMPTY",
            level="WARNING",
            message=(
                "Transcription vide — audio absent ou inaudible "
                f"(filename={filename})"
            ),
            extra={"operation": "video_transcribe", "filename": filename},
        )
        raise VideoFatalError(
            "transcription vide : la vidéo ne contient pas d'audio "
            "compréhensible"
        )

    log_event(
        "VIDEO_WHISPER_OK",
        message=(
            f"Transcribed | lang={info.language} "
            f"| chars={len(text)}"
        ),
        extra={
            "operation": "video_transcribe",
            "language": getattr(info, "language", ""),
            "chars": len(text),
        },
    )
    return text


def resolve_transcriber():
    """Choisit le transcriber selon la config et la disponibilité.

    Retourne un callable signature-compatible (local_path, audio_path,
    filename, duration) -> str.
    """
    mode = VIDEO_TRANSCRIPTION_MODE

    if mode == "offline":
        return None  # bouchon par défaut (ingest._default_transcriber)

    if mode == "whisper" and not _whisper_available():
        from app.graph.subgraphs.video.ingest import VideoFatalError

        raise VideoFatalError(
            "VIDEO_TRANSCRIPTION_MODE=whisper mais faster-whisper "
            "n'est pas installé (pip install faster-whisper)"
        )

    if mode == "auto" and not _whisper_available():
        log_event(
            "VIDEO_TRANSCRIPTION_FALLBACK",
            level="WARNING",
            message=(
                "faster-whisper absent — repli sur le bouchon "
                "pédagogique (installer faster-whisper pour la "
                "transcription réelle)"
            ),
            extra={"operation": "video_transcribe"},
        )
        return None

    return whisper_transcriber


__all__ = [
    "resolve_transcriber",
    "whisper_transcriber",
]
