# VideoSubgraph — INDEX/PERSIST : la vidéo devient une SOURCE DE
# CONNAISSANCE (§28/§30).
#
# VideoKnowledgeStore : deux backends, UNE SEULE API.
#   - PostgreSQL (Neon) si DATABASE_URL est définie : tables videos +
#     video_segments ( embedding pgvector ) ;
#   - sinon JSON sur disque ( registre par utilisateur + un fichier de
#     contenu par vidéo ) : comportement historique strictement conservé.
#
# Avant ce dual-dialecte, le store écrivait dans le dossier TEMP du
# conteneur Render : transcript et segments étaient PERDUS à chaque
# redéploiement, et la recherche vidéo tournait sur une base vide.
#
# Les clés knowledge retournées (`video://<user>/<video_id>`) alimentent
# VideoResult.knowledge_keys. Le RETRIEVAL (retrieval.py) lit
# UNIQUEMENT cette sortie persistée : jamais de ré-ingestion à la
# question (mission : « ne pas retranscrire la vidéo à chaque question »).
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from app.config import DATABASE_URL, USE_POSTGRES
from app.schemas.video import PedagogicalSegment

_SLUG_RE = re.compile(r"[^a-zA-Z0-9_-]")


def _slug(value: str) -> str:
    cleaned = _SLUG_RE.sub("", str(value))
    return cleaned or "video"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pg_url() -> str:
    """URL SQLAlchemy psycopg3 ( cf. persistence._postgres_url )."""
    scheme, rest = DATABASE_URL.split("://", 1)
    if scheme in ("postgres", "postgresql"):
        return f"postgresql+psycopg://{rest}"
    return DATABASE_URL


def _segment_embedding(segment: dict, text: str = "") -> list[float] | None:
    """Embedding d'un segment ( title + summary + topics + texte ).

    Retourne None si le provider est indisponible — l'insert se fait
    alors sans vecteur ( la recherche lexical reste fonctionnelle ),
    jamais d'exception (§15 fail-safe ).
    """
    try:
        from app.services.context.semantic.provider import (
            get_embedding_provider,
        )

        blob = " ".join(
            [
                str(segment.get("title") or ""),
                str(segment.get("summary") or ""),
                " ".join(segment.get("topics") or []),
                text or "",
            ]
        )
        provider = get_embedding_provider()
        return provider.embed_text(blob)
    except Exception:
        return None


def _vec_literal(vec: list[float] | None) -> str | None:
    """Représentation littérale pgvector, ou None si pas de vecteur."""
    if vec is None:
        return None
    return "[" + ",".join(repr(float(v)) for v in vec) + "]"


class VideoKnowledgeStore:
    """Stockage de la connaissance vidéo ( isolé par user ).

    PostgreSQL ( Neon ) si DATABASE_URL, sinon JSON local.
    API identique dans les deux cas — retrieval.py n'est pas modifié.
    """

    def __init__(self, root_dir: str | Path | None = None):
        # root_dir n'est utilisé qu'en mode JSON ( tests/dev locaux ).
        self._root = Path(root_dir) if root_dir else None
        self._registry_path = (
            self._root / "video_knowledge.json" if self._root else None
        )

    @property
    def _is_postgres(self) -> bool:
        return bool(USE_POSTGRES and DATABASE_URL)

    # ------------------------------------------------------------------
    # Persistance (index)
    # ------------------------------------------------------------------
    def persist_video(
        self,
        *,
        video_id: str,
        user_id: str,
        filename: str,
        source_url: str,
        duration: float = 0.0,
        transcript: str = "",
        segments: list[dict] | None = None,
        segment_texts: list[str] | None = None,
        metadata: dict | None = None,
        created_at: str = "",
        media_object_id: str | None = None,
    ) -> list[str]:
        """Indexe une vidéo → clés knowledge créées.

        Le contenu ( segments validés + transcript + métadonnées ) est
        persisté en base ( Neon ) ou sous un fichier par vidéo ( local ).
        """
        if not user_id:
            raise ValueError("user_id requis pour indexer une vidéo")
        if not video_id:
            raise ValueError("video_id requis pour indexer une vidéo")

        validated_segments = [
            PedagogicalSegment(**s).model_dump() for s in (segments or [])
        ]
        key = f"video://{user_id}/{video_id}"
        created = created_at or _now_iso()

        if self._is_postgres:
            self._persist_video_pg(
                video_id=video_id,
                user_id=user_id,
                filename=filename,
                source_url=source_url,
                duration=duration,
                transcript=transcript,
                segments=validated_segments,
                segment_texts=segment_texts,
                created=created,
                media_object_id=media_object_id,
            )
            return [key]

        # --- mode JSON local ( historique ) -----------------------------
        assert self._root is not None
        self._root.mkdir(parents=True, exist_ok=True)
        payload = {
            "knowledge_key": key,
            "video_id": video_id,
            "user_id": user_id,
            "filename": filename,
            "source_url": source_url,
            "duration": float(duration or 0.0),
            "created_at": created,
            "transcript": transcript,
            "segments": validated_segments,
            "segment_texts": list(segment_texts or []),
            "metadata": dict(metadata or {}),
        }
        content_path = self._root / f"{_slug(video_id)}.json"
        content_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        registry = self._registry()
        registry.setdefault("videos", {})[video_id] = {
            "video_id": video_id,
            "user_id": user_id,
            "filename": filename,
            "knowledge_key": key,
            "created_at": created,
        }
        self._write_registry(registry)
        return [key]

    def _persist_video_pg(
        self,
        *,
        video_id,
        user_id,
        filename,
        source_url,
        duration,
        transcript,
        segments,
        segment_texts,
        created,
        media_object_id,
    ) -> None:
        from sqlalchemy import create_engine, text

        texts = list(segment_texts or [])
        engine = create_engine(_pg_url(), pool_pre_ping=True)
        try:
            with engine.begin() as conn:
                # Upsert : une ré-indexation de la même vidéo remplace
                # l'ancien contenu. ON DELETE CASCADE supprime les
                # anciens segments ( fini la connaissance orpheline ).
                conn.execute(
                    text(
                        """INSERT INTO videos
                           (video_id, user_id, filename, source_url, duration,
                            knowledge_key, transcript, media_object_id,
                            created_at)
                           VALUES (:vid, :uid, :filename, :source_url, :dur,
                                   :key, :transcript, :moid, :created)
                           ON CONFLICT (video_id) DO UPDATE SET
                               filename = EXCLUDED.filename,
                               source_url = EXCLUDED.source_url,
                               duration = EXCLUDED.duration,
                               transcript = EXCLUDED.transcript,
                               media_object_id = EXCLUDED.media_object_id"""
                    ),
                    {
                        "vid": video_id,
                        "uid": user_id,
                        "filename": filename,
                        "source_url": source_url or "",
                        "dur": float(duration or 0.0),
                        "key": f"video://{user_id}/{video_id}",
                        "transcript": transcript or "",
                        "moid": media_object_id,
                        "created": created,
                    },
                )
                conn.execute(
                    text(
                        "DELETE FROM video_segments WHERE video_id = :vid"
                    ),
                    {"vid": video_id},
                )
                for idx, seg in enumerate(segments):
                    txt = texts[idx] if idx < len(texts) else ""
                    vec = _segment_embedding(seg, txt)
                    lit = _vec_literal(vec)
                    conn.execute(
                        text(
                            """INSERT INTO video_segments
                               (video_id, idx, title, summary, start,
                                "end", topics, embedding, created_at)
                               VALUES (:vid, :idx, :title, :summary, :start,
                                       :end, CAST(:topics AS jsonb),
                                       """ + (
                                           "CAST(:emb AS vector)" if lit else "NULL"
                                       ) + """, :created)"""
                        ),
                        {
                            "vid": video_id,
                            "idx": idx,
                            "title": str(seg.get("title") or ""),
                            "summary": str(seg.get("summary") or ""),
                            "start": float(seg.get("start") or 0.0),
                            "end": float(seg.get("end") or 0.0),
                            "topics": json.dumps(
                                seg.get("topics") or [], ensure_ascii=False
                            ),
                            "emb": lit,
                            "created": created,
                        },
                    )
        finally:
            engine.dispose()

    def _registry(self) -> dict:
        if self._registry_path is None or not self._registry_path.exists():
            return {"videos": {}}
        try:
            return json.loads(self._registry_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"videos": {}}

    def _write_registry(self, registry: dict) -> None:
        assert self._registry_path is not None
        tmp = self._registry_path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(registry, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self._registry_path)

    # ------------------------------------------------------------------
    # Lecture (retrieval — SANS ré-ingestion)
    # ------------------------------------------------------------------
    def get_video(self, user_id: str, video_id: str) -> dict | None:
        """Charge une vidéo STOCKÉE (None si absente / autre user)."""
        if self._is_postgres:
            return self._get_video_pg(user_id, video_id)

        info = self._registry().get("videos", {}).get(video_id)
        if not info or info.get("user_id") != user_id:
            return None
        assert self._root is not None
        content_path = self._root / f"{_slug(video_id)}.json"
        if not content_path.exists():
            return None
        try:
            return json.loads(content_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _get_video_pg(self, user_id: str, video_id: str) -> dict | None:
        from sqlalchemy import create_engine, text

        engine = create_engine(_pg_url(), pool_pre_ping=True)
        try:
            with engine.connect() as conn:
                vrow = conn.execute(
                    text(
                        """SELECT video_id, user_id, filename, source_url,
                                  duration, knowledge_key, transcript,
                                  created_at
                           FROM videos
                           WHERE video_id = :vid AND user_id = :uid"""
                    ),
                    {"vid": video_id, "uid": user_id},
                ).fetchone()
                if vrow is None:
                    return None
                vm = vrow._mapping
                srows = conn.execute(
                    text(
                        """SELECT idx, title, summary, start, "end", topics
                           FROM video_segments
                           WHERE video_id = :vid
                           ORDER BY idx"""
                    ),
                    {"vid": video_id},
                ).fetchall()
        finally:
            engine.dispose()

        segments = [
            {
                "title": r._mapping["title"],
                "summary": r._mapping["summary"],
                "start": r._mapping["start"],
                "end": r._mapping["end"],
                "topics": list(r._mapping["topics"] or []),
            }
            for r in srows
        ]
        return {
            "knowledge_key": vm["knowledge_key"],
            "video_id": vm["video_id"],
            "user_id": vm["user_id"],
            "filename": vm["filename"],
            "source_url": vm["source_url"],
            "duration": vm["duration"],
            "created_at": vm["created_at"],
            "transcript": vm["transcript"],
            "segments": segments,
            "segment_texts": [],  # non persisté en PG : dérivé du transcript
            "metadata": {},
        }

    def list_videos(self, user_id: str) -> list[dict]:
        """Liste les vidéos indexées d'un utilisateur (infos seules)."""
        if self._is_postgres:
            from sqlalchemy import create_engine, text

            engine = create_engine(_pg_url(), pool_pre_ping=True)
            try:
                with engine.connect() as conn:
                    rows = conn.execute(
                        text(
                            """SELECT video_id, user_id, filename,
                                      knowledge_key, created_at
                               FROM videos WHERE user_id = :uid
                               ORDER BY created_at DESC"""
                        ),
                        {"uid": user_id},
                    ).fetchall()
            finally:
                engine.dispose()
            return [
                {
                    "video_id": r._mapping["video_id"],
                    "user_id": r._mapping["user_id"],
                    "filename": r._mapping["filename"],
                    "knowledge_key": r._mapping["knowledge_key"],
                    "created_at": r._mapping["created_at"],
                }
                for r in rows
            ]

        return [
            info
            for info in self._registry().get("videos", {}).values()
            if info.get("user_id") == user_id
        ]

    @property
    def root(self) -> Path:
        # Racine JSON ( uniquement utilisée en mode local / tests ).
        return self._root or Path(".")


__all__ = ["VideoKnowledgeStore"]
