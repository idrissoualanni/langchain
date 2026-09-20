# VideoSubgraph — enrichissement des métadonnées (§28).
#
# Ajoute au canal `metadata` les champs persistés (source, format,
# durée, langue détectée, créé à, volumes mots/segments) à partir des
# données brutes produites par les services. Pur et déterministe.
from __future__ import annotations

import datetime
import re

from app.graph.subgraphs.video.schemas import VideoMetadata

_WORD_RE = re.compile(r"[a-zA-ZÀ-ÿà-ÿ0-9]+")

_FR_STOP = {"le", "la", "les", "de", "des", "du", "et", "est", "que", "une", "un"}
_EN_STOP = {"the", "is", "are", "of", "and", "to", "in", "for", "with"}


def detect_language(text: str) -> str:
    """Détection heuristique fr/en/unknown (déterministe, hors-ligne)."""
    words = [w.lower() for w in _WORD_RE.findall(text or "")]
    if not words:
        return "unknown"
    fr = sum(1 for w in words if w in _FR_STOP)
    en = sum(1 for w in words if w in _EN_STOP)
    if fr >= en and fr > 0:
        return "fr"
    if en > fr and en > 0:
        return "en"
    return "unknown"


def now_utc_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def enrich_video_metadata(
    *,
    video_id: str,
    user_id: str,
    filename: str,
    origin: str,
    duration: float,
    fmt: str,
    transcript: str,
    segments: list[dict],
) -> dict:
    """Construit les métadonnées enrichies (VideoMetadata validé)."""
    words = _WORD_RE.findall(transcript or "")
    meta = VideoMetadata(
        video_id=video_id,
        user_id=user_id,
        filename=filename,
        source=origin,
        duration=float(duration or 0.0),
        format=fmt,
        language=detect_language(transcript or ""),
        created_at=now_utc_iso(),
        word_count=len(words),
        segment_count=len(segments or []),
        knowledge_keys=[],
    )
    return meta.model_dump()


__all__ = [
    "detect_language",
    "enrich_video_metadata",
    "now_utc_iso",
]