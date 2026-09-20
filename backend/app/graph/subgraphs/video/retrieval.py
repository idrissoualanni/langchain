# VideoSubgraph — RETRIEVAL du transcript STOCKÉ.
#
# Répond à une question sur une vidéo SANS ré-ingestion ni
# re-transcription : il lit uniquement la sortie persistée produite par
# le subgraph d'ingestion (VideoKnowledgeStore). Le node/état d'ingestion
# ne s'exécute donc JAMAIS au moment de la question (mission : la sortie
# stockée sert au retrieval).
#
# API publique :
#   get_default_store()                → store racine par défaut (temp)
#   get_video(user_id, video_id)       → vidéo stockée
#   get_video_segments(...)            → segments stockés
#   search_video_segments(...)         → recherche bornée (statuts
#                                        contrôlés found/insufficient/
#                                        unavailable/error)
from __future__ import annotations

import re
import tempfile
from pathlib import Path

from app.graph.subgraphs.video.persist import VideoKnowledgeStore

_WORD_RE = re.compile(r"[a-zA-ZÀ-ÿà-ÿ0-9]+")

_SEARCH_STOPWORDS = {
    "le", "la", "les", "de", "des", "du", "un", "une", "et", "ou",
    "que", "qui", "pour", "avec", "dans", "sur", "est", "the", "and",
    "of", "to", "in", "for", "que", "sur", "video", "vidéo", "cette",
    "explique", "expliquer", "parler", "parle",
}


def default_store_dir() -> Path:
    """Racine de stockage par défaut (hors-ligne, sous le temp système).

    Un agent de wiring peut fournir une racine persistante réelle ;
    cette valeur n'écrit rien dans le dépôt.
    """
    return Path(tempfile.gettempdir()) / "video_subgraph" / "store"


def get_default_store() -> VideoKnowledgeStore:
    return VideoKnowledgeStore(default_store_dir())


def _tokens(text: str) -> set[str]:
    return {
        w
        for w in _WORD_RE.findall((text or "").lower())
        if len(w) >= 3 and w not in _SEARCH_STOPWORDS
    }


def _segment_text(segment: dict, text: str = "") -> str:
    topics = " ".join(segment.get("topics") or [])
    return " ".join(
        [
            str(segment.get("title") or ""),
            str(segment.get("summary") or ""),
            topics,
            text or "",
        ]
    )


def _score_segment(
    segment: dict, text: str, query_tokens: set[str], query_norm: str
) -> float:
    blob = _segment_text(segment, text)
    normalized = re.sub(r"\s+", " ", blob.lower()).strip()
    if not query_tokens or not normalized:
        return 0.0
    tokens = _tokens(normalized)
    if not tokens:
        return 0.0
    overlap = len(query_tokens & tokens)
    score = overlap / len(query_tokens)
    if query_norm and query_norm in " " + normalized + " ":
        score += 0.2
    return round(min(1.0, score), 3)


def get_video(
    user_id: str, video_id: str, store: VideoKnowledgeStore | None = None
) -> dict | None:
    """Vidéo stockée (payload complet) — None si absente/inaccessible."""
    return (store or get_default_store()).get_video(user_id, video_id)


def get_video_segments(
    user_id: str,
    video_id: str,
    store: VideoKnowledgeStore | None = None,
) -> list[dict]:
    """Segments stockés d'une vidéo ([] si non disponible)."""
    payload = get_video(user_id, video_id, store)
    if not payload:
        return []
    return list(payload.get("segments") or [])


def search_video_segments(
    user_id: str,
    query: str,
    *,
    video_id: str | None = None,
    store: VideoKnowledgeStore | None = None,
    limit: int = 3,
) -> dict:
    """Recherche dans les segments STOCKÉS (jamais de réseau).

    Retourne un dict contrôlé (style SearchResponse V6.5) :
      {status: found|insufficient|unavailable|error, query, results,
       error}
    results = [{video_id, filename, segment, relevance}]
    """
    store = store or get_default_store()
    sq = (query or "").strip()
    if not user_id or not sq:
        return {"status": "unavailable", "query": sq, "results": [], "error": ""}
    try:
        candidates: list[dict] = []
        if video_id:
            payload = store.get_video(user_id, video_id)
            candidates = [payload] if payload else []
        else:
            candidates = []
            for info in store.list_videos(user_id):
                vid = info.get("video_id") or ""
                if not vid:
                    # rétro-compat : registres écrits sans video_id
                    key = info.get("knowledge_key") or ""
                    vid = key.rsplit("/", 1)[-1] if key else ""
                payload = store.get_video(user_id, vid) if vid else None
                if payload:
                    candidates.append(payload)
        candidates = [c for c in candidates if c]

        query_tokens = _tokens(sq)
        query_norm = re.sub(r"\s+", " ", sq.lower()).strip()

        scored: list[dict] = []
        for payload in candidates:
            texts: list[str] = list(payload.get("segment_texts") or []) or (
                list((payload.get("metadata") or {}).get("segment_texts") or [])
            )
            for index, segment in enumerate(payload.get("segments") or []):
                text = texts[index] if index < len(texts) else ""
                relevance = _score_segment(segment, text, query_tokens, query_norm)
                if relevance <= 0:
                    continue
                scored.append(
                    {
                        "video_id": payload.get("video_id", ""),
                        "filename": payload.get("filename", ""),
                        "knowledge_key": payload.get("knowledge_key", ""),
                        "segment": segment,
                        "relevance": relevance,
                    }
                )
        scored.sort(key=lambda r: r["relevance"], reverse=True)
        results = scored[: max(1, min(int(limit), 20))]

        if not candidates:
            status = "unavailable"
        elif results:
            status = "found"
        else:
            status = "insufficient"
        return {"status": status, "query": sq, "results": results, "error": ""}
    except Exception as exc:  # pragma: no cover — défensif
        return {
            "status": "error",
            "query": sq,
            "results": [],
            "error": str(exc),
        }


__all__ = [
    "default_store_dir",
    "get_default_store",
    "get_video",
    "get_video_segments",
    "search_video_segments",
]