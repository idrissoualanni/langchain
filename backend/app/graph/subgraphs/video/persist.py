# VideoSubgraph — INDEX/PERSIST : la vidéo devient une SOURCE DE
# CONNAISSANCE (§28/§30).
#
# VideoKnowledgeStore : registre JSON par utilisateur + un fichier de
# contenu par vidéo (transcript + segments + métadonnées). Déterministe,
# hors-ligne et isolé par user_id. Les clés knowledge retournées
# (`video://<user>/<video_id>`) alimentent VideoResult.knowledge_keys —
# le wiring vers le RAG réel reste à la charge d'un autre agent.
#
# Le RETRIEVAL (retrieval.py) lit UNIQUEMENT cette sortie persistée :
# jamais de ré-ingestion à la question (mission : « ne pas retranscrire
# la vidéo à chaque question »).
from __future__ import annotations

import json
import re
from pathlib import Path

from app.schemas.video import PedagogicalSegment

_SLUG_RE = re.compile(r"[^a-zA-Z0-9_-]")


def _slug(value: str) -> str:
    cleaned = _SLUG_RE.sub("", str(value))
    return cleaned or "video"


class VideoKnowledgeStore:
    """Stockage JSON de la connaissance vidéo (isolé par user)."""

    def __init__(self, root_dir: str | Path):
        self._root = Path(root_dir)
        self._registry_path = self._root / "video_knowledge.json"

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
    ) -> list[str]:
        """Indexe une vidéo → clés knowledge créées.

        Le contenu (segments validés + transcript + métadonnées) est
        persisté sous un fichier par vidéo ; le registre indexe les
        vidéos d'un utilisateur.
        """
        if not user_id:
            raise ValueError("user_id requis pour indexer une vidéo")
        if not video_id:
            raise ValueError("video_id requis pour indexer une vidéo")

        validated_segments = [
            PedagogicalSegment(**s).model_dump() for s in (segments or [])
        ]
        key = f"video://{user_id}/{video_id}"

        self._root.mkdir(parents=True, exist_ok=True)
        payload = {
            "knowledge_key": key,
            "video_id": video_id,
            "user_id": user_id,
            "filename": filename,
            "source_url": source_url,
            "duration": float(duration or 0.0),
            "created_at": created_at,
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
            "created_at": created_at,
        }
        self._write_registry(registry)
        return [key]

    def _registry(self) -> dict:
        if self._registry_path.exists():
            try:
                return json.loads(self._registry_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {"videos": {}}
        return {"videos": {}}

    def _write_registry(self, registry: dict) -> None:
        tmp = self._registry_path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp.replace(self._registry_path)

    # ------------------------------------------------------------------
    # Lecture (retrieval — SANS ré-ingestion)
    # ------------------------------------------------------------------
    def get_video(self, user_id: str, video_id: str) -> dict | None:
        """Charge une vidéo STOCKÉE (None si absente / autre user)."""
        info = self._registry().get("videos", {}).get(video_id)
        if not info or info.get("user_id") != user_id:
            return None
        content_path = self._root / f"{_slug(video_id)}.json"
        if not content_path.exists():
            return None
        try:
            return json.loads(content_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def list_videos(self, user_id: str) -> list[dict]:
        """Liste les vidéos indexées d'un utilisateur (infos seules)."""
        return [
            info
            for info in self._registry().get("videos", {}).values()
            if info.get("user_id") == user_id
        ]

    @property
    def root(self) -> Path:
        return self._root


__all__ = ["VideoKnowledgeStore"]