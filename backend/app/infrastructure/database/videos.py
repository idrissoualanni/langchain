# VideoSubgraph v2 — repository PostgreSQL (Neon) pour la persistance
# vidéo. Remplace le store JSON ephémere ( tempfile — perdu a chaque
# redéploiement Render ).
#
# Tables ( connections.py SCHEMA_STATEMENTS ) :
#   videos          : une ligne par vidéo ingérée ( transcript +,
#                     optionnellement, description visuelle de l'agent ) ;
#   video_segments  : segments pédagogiques ( segmentation transcript ).
#
# Pattern : get_conn() thread-local + execute(text, params nommés) +
# commit() — identique a threads.py. JSONB evite ( types TEXT/REAL,
# portables SQLite/PostgreSQL ; topics = liste JSON serialisee ).
#
# Isolation : toutes les requêtes filtrent par user_id ( jamais confiance
# en video_id seul ) — un utilisateur ne peut lire que SES vidéos.
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from app.infrastructure.database.connections import get_conn
from app.logging.events import log_event


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_video(row) -> dict:
    """Ligne SQL -> payload vidéo ( API compatible VideoKnowledgeStore )."""
    if row is None:
        return None
    d = dict(row)
    return {
        "knowledge_key": d.get("knowledge_key", ""),
        "video_id": d.get("video_id", ""),
        "user_id": d.get("user_id", ""),
        "filename": d.get("filename", ""),
        "source_url": d.get("source_url", ""),
        "duration": float(d.get("duration") or 0.0),
        "created_at": d.get("created_at", ""),
        "transcript": d.get("transcript", ""),
        "visual_description": d.get("visual_description", ""),
        "segments": [],  # rempli par _load_segments si besoin
        "segment_texts": [],
        "metadata": {
            "origin": d.get("origin", ""),
            "format": d.get("format", ""),
            "language": d.get("language", ""),
        },
    }


def persist_video(
    *,
    video_id: str,
    user_id: str,
    filename: str,
    source_url: str,
    duration: float = 0.0,
    origin: str = "",
    fmt: str = "",
    language: str = "",
    transcript: str = "",
    visual_description: str = "",
    segments: list[dict] | None = None,
    segment_texts: list[str] | None = None,
    metadata: dict | None = None,
    created_at: str = "",
) -> list[str]:
    """Indexe une vidéo en base → clés knowledge créées.

    Remplace VideoKnowledgeStore.persist_video : DELETE puis INSERT de
    la vidéo et de ses segments ( idempotent — re-ingestion permise ).
    """
    if not user_id:
        raise ValueError("user_id requis pour indexer une vidéo")
    if not video_id:
        raise ValueError("video_id requis pour indexer une vidéo")

    key = f"video://{user_id}/{video_id}"
    now = created_at or _now_utc()
    meta = dict(metadata or {})
    if origin:
        meta["origin"] = origin
    if fmt:
        meta["format"] = fmt
    if language:
        meta["language"] = language

    conn = get_conn()
    conn.execute(
        "DELETE FROM video_segments WHERE video_id = :video_id",
        {"video_id": video_id},
    )
    conn.execute(
        "DELETE FROM videos WHERE video_id = :video_id",
        {"video_id": video_id},
    )
    conn.execute(
        """
        INSERT INTO videos (
            video_id, user_id, filename, source_url, duration, origin,
            format, language, transcript, visual_description,
            knowledge_key, created_at
        ) VALUES (
            :video_id, :user_id, :filename, :source_url, :duration,
            :origin, :format, :language, :transcript,
            :visual_description, :knowledge_key, :created_at
        )
        """,
        {
            "video_id": video_id,
            "user_id": user_id,
            "filename": filename,
            "source_url": source_url or "",
            "duration": float(duration or 0.0),
            "origin": origin,
            "format": fmt,
            "language": language,
            "transcript": transcript or "",
            "visual_description": visual_description or "",
            "knowledge_key": key,
            "created_at": now,
        },
    )

    texts = list(segment_texts or [])
    segs = [
        (s or {}) for s in (segments or [])
    ]
    for index, seg in enumerate(segs):
        conn.execute(
            """
            INSERT INTO video_segments (
                id, video_id, user_id, title, summary, start, end,
                topics, segment_text, created_at
            ) VALUES (
                :id, :video_id, :user_id, :title, :summary, :start, :end,
                :topics, :segment_text, :created_at
            )
            """,
            {
                "id": seg.get("id") or f"{video_id}-seg-{uuid.uuid4().hex[:8]}",
                "video_id": video_id,
                "user_id": user_id,
                "title": str(seg.get("title") or "")[:200],
                "summary": str(seg.get("summary") or "")[:1000],
                "start": float(seg.get("start") or 0.0),
                "end": float(seg.get("end") or 0.0),
                "topics": json.dumps(
                    [str(t) for t in (seg.get("topics") or [])],
                    ensure_ascii=False,
                ),
                "segment_text": (
                    texts[index] if index < len(texts) else ""
                ),
                "created_at": now,
            },
        )

    conn.commit()

    log_event(
        "VIDEO_INDEXED",
        message=f"Vidéo indexée en base | video_id={video_id} | segments={len(segs)}",
        user_id=user_id,
        extra={
            "operation": "video_persist",
            "video_id": video_id,
            "segments": len(segs),
        },
    )
    return [key]


def _load_segments(conn, video_id: str, user_id: str) -> tuple[list[dict], list[str]]:
    rows = conn.execute(
        """
        SELECT title, summary, start, end, topics, segment_text
        FROM video_segments
        WHERE video_id = :video_id AND user_id = :user_id
        ORDER BY start ASC
        """,
        {"video_id": video_id, "user_id": user_id},
    ).fetchall()

    segments: list[dict] = []
    texts: list[str] = []
    for row in rows:
        d = dict(row)
        try:
            topics = json.loads(d.get("topics") or "[]")
        except (json.JSONDecodeError, TypeError):
            topics = []
        segments.append(
            {
                "title": d.get("title", ""),
                "summary": d.get("summary", ""),
                "start": float(d.get("start") or 0.0),
                "end": float(d.get("end") or 0.0),
                "topics": topics,
            }
        )
        texts.append(d.get("segment_text") or "")
    return segments, texts


def get_video(user_id: str, video_id: str) -> dict | None:
    """Charge une vidéo STOCKÉE (None si absente / autre utilisateur).

    Le filtre user_id est TOUJOURS appliqué ( isolation ).
    """
    row = get_conn().execute(
        """
        SELECT video_id, user_id, filename, source_url, duration, origin,
               format, language, transcript, visual_description,
               knowledge_key, created_at
        FROM videos
        WHERE video_id = :video_id AND user_id = :user_id
        """,
        {"video_id": video_id, "user_id": user_id},
    ).fetchone()
    if row is None:
        return None
    payload = _row_to_video(row)
    payload["segments"], payload["segment_texts"] = _load_segments(
        get_conn(), video_id, user_id
    )
    return payload


def list_videos(user_id: str) -> list[dict]:
    """Liste les vidéos indexées d'un utilisateur (infos seules)."""
    rows = get_conn().execute(
        """
        SELECT video_id, user_id, filename, knowledge_key, created_at
        FROM videos
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        """,
        {"user_id": user_id},
    ).fetchall()
    return [dict(row) for row in rows]


def get_video_segments(user_id: str, video_id: str) -> list[dict]:
    """Segments stockés d'une vidéo ([] si non disponible)."""
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM videos WHERE video_id = :video_id AND user_id = :user_id",
        {"video_id": video_id, "user_id": user_id},
    ).fetchone()
    if row is None:
        return []
    segments, _ = _load_segments(conn, video_id, user_id)
    return segments


def search_video_segments(
    user_id: str,
    query: str,
    *,
    video_id: str | None = None,
    limit: int = 3,
) -> dict:
    """Recherche bornée dans les segments stockés (jamais de réseau).

    Statuts contrôlés ( style SearchResponse V6.5 ) :
      found | insufficient | unavailable | error
    """
    sq = (query or "").strip()
    if not user_id or not sq:
        return {"status": "unavailable", "query": sq, "results": [], "error": ""}

    try:
        import re

        _WORD_RE = re.compile(r"[a-zA-ZÀ-ÿà-ÿ0-9]+")
        _STOP = {
            "le", "la", "les", "de", "des", "du", "un", "une", "et", "ou",
            "que", "qui", "pour", "avec", "dans", "sur", "est", "the", "and",
            "of", "to", "in", "for", "video", "vidéo", "cette", "explique",
        }

        def tokens(text: str) -> set[str]:
            return {
                w
                for w in _WORD_RE.findall((text or "").lower())
                if len(w) >= 3 and w not in _STOP
            }

        query_tokens = tokens(sq)
        query_norm = re.sub(r"\s+", " ", sq.lower()).strip()

        conn = get_conn()
        if video_id:
            videos = [
                v
                for v in [get_video(user_id, video_id)]
                if v
            ]
        else:
            videos = []
            for info in list_videos(user_id):
                v = get_video(user_id, info.get("video_id", ""))
                if v:
                    videos.append(v)

        scored: list[dict] = []
        for payload in videos:
            texts = list(payload.get("segment_texts") or [])
            for index, segment in enumerate(payload.get("segments") or []):
                text = texts[index] if index < len(texts) else ""
                blob = " ".join(
                    [
                        str(segment.get("title") or ""),
                        str(segment.get("summary") or ""),
                        " ".join(str(t) for t in (segment.get("topics") or [])),
                        text or "",
                    ]
                )
                normalized = re.sub(r"\s+", " ", blob.lower()).strip()
                if not query_tokens or not normalized:
                    continue
                seg_tokens = tokens(normalized)
                if not seg_tokens:
                    continue
                overlap = len(query_tokens & seg_tokens)
                score = overlap / len(query_tokens)
                if query_norm and query_norm in " " + normalized + " ":
                    score += 0.2
                score = round(min(1.0, score), 3)
                if score <= 0:
                    continue
                scored.append(
                    {
                        "video_id": payload.get("video_id", ""),
                        "filename": payload.get("filename", ""),
                        "knowledge_key": payload.get("knowledge_key", ""),
                        "segment": segment,
                        "relevance": score,
                    }
                )
        scored.sort(key=lambda r: r["relevance"], reverse=True)
        results = scored[: max(1, min(int(limit), 20))]

        if not videos:
            status = "unavailable"
        elif results:
            status = "found"
        else:
            status = "insufficient"
        return {"status": status, "query": sq, "results": results, "error": ""}
    except Exception as exc:  # noqa: BLE001 — défensif
        return {
            "status": "error",
            "query": sq,
            "results": [],
            "error": str(exc),
        }


__all__ = [
    "get_video",
    "get_video_segments",
    "list_videos",
    "persist_video",
    "search_video_segments",
]
