# VideoSubgraph — schémas Pydantic (validation stricte extra=forbid).
#
#   PedagogicalSegment : unité pédagogique issue de la segmentation
#                        (title/summary/start/end/topics) — validée par
#                        le service vidéo_segment (validation Pydantic,
#                        mission § video_segment).
#   VideoUploadPayload : entrée workflow validée avant ingestion.
#   VideoMetadata      : métadonnées enrichies persistées (knowledge).
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class PedagogicalSegment(BaseModel):
    """UN segment pédagogique issu de la segmentation d'un transcript."""

    model_config = {"extra": "forbid"}

    title: str = Field(description="Titre déterministe du segment")
    summary: str = Field(default="", description="Résumé/1re phrase")
    start: float = Field(default=0.0, ge=0.0, description="Début (s)")
    end: float = Field(default=0.0, ge=0.0, description="Fin (s)")
    topics: list[str] = Field(
        default_factory=list, description="Sujets dominants détectés"
    )

    @field_validator("start")
    @classmethod
    def _start_non_neg(cls, value: float) -> float:
        if value < 0:
            raise ValueError("start ne peut pas être négatif")
        return value

    @field_validator("end")
    @classmethod
    def _end_non_neg(cls, value: float) -> float:
        if value < 0:
            raise ValueError("end ne peut pas être négatif")
        return value

    @model_validator(mode="after")
    def _end_after_start(self) -> "PedagogicalSegment":
        if self.end < self.start:
            raise ValueError(
                f"end ({self.end}) < start ({self.start}): segment invalide"
            )
        return self


class VideoUploadPayload(BaseModel):
    """Entrée normalisée de l'ingestion (validée avant tout traitement).

    Privilégie la source locale (chemin ou file://) pour un
    fonctionnement hors-ligne ; une source http(s) nécessite un
    downloader injecté (jamais de demande réseau par défaut).
    """

    model_config = {"extra": "forbid"}

    video_id: str = Field(
        default="", description="Identifiant (auto-généré si vide)"
    )
    filename: str = Field(description="Nom de fichier source")
    source_url: str = Field(description="Chemin local, file:// ou URL")
    duration: float = Field(default=0.0, ge=0.0)
    options: dict = Field(
        default_factory=dict,
        description="max_attempts, working_dir, store_dir, "
        "download_options…",
    )


class VideoMetadata(BaseModel):
    """Métadonnées enrichies de la vidéo (persistées en knowledge)."""

    model_config = {"extra": "forbid"}

    video_id: str = ""
    user_id: str = ""
    filename: str = ""
    source: str = Field(
        default="", description="Origine de la source (local/remote)"
    )
    duration: float = Field(default=0.0, ge=0.0)
    format: str = Field(default="", description="Extension média normalisée")
    language: str = Field(
        default="", description="Langue détectée (fr/en/unknown)"
    )
    created_at: str = Field(
        default="", description="Horodatage ISO 8601 UTC"
    )
    word_count: int = Field(default=0, ge=0)
    segment_count: int = Field(default=0, ge=0)
    knowledge_keys: list[str] = Field(default_factory=list)


__all__ = [
    "PedagogicalSegment",
    "VideoMetadata",
    "VideoUploadPayload",
]