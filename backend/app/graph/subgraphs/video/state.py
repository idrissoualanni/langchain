# VideoSubgraph — VideoState typé (§7/§28).
#
# État INTERNE du subgraph : jamais exposé au Main Graph (frontière
# §5/§8). L'entrée (source_url, filename, user_id…) est normalisée par
# validate_upload ; la sortie structurée est rendue dans le canal
# `result` (VideoResult §8) via le node finalize. Les nodes internes
# lisent/écrivent les canaux ci-dessous.
#
# Champs spec de la mission :
#   video_id / user_id / filename / source_url / local_path / duration /
#   audio_path / transcript_path / segments / metadata / status /
#   progress / errors / iteration / max_attempts / result.
#
# `thread_id` est ajouté pour l'identité de logging (même rôle que dans
# ProblemState). `metadata` porte les infos dérivées (working_dir,
# store_dir, origin, format, transcript, language, knowledge_keys).
from typing import TypedDict


class VideoState(TypedDict, total=False):
    """État interne du VideoSubgraph (§28)."""

    # --- Entrée (normalisée par validate_upload) ---
    video_id: str
    user_id: str
    thread_id: str
    filename: str
    source_url: str
    duration: float

    # --- Phase ingestion (service video_ingest interne) ---
    local_path: str
    audio_path: str
    transcript_path: str

    # --- Phase segmentation (service video_segment interne) ---
    segments: list

    # --- Métadonnées enrichies + info technique (dict libre) ---
    metadata: dict

    # --- Pilotage d'état (statuts bornés + progression) ---
    status: str
    progress: float
    errors: list
    iteration: int
    max_attempts: int

    # --- Sortie (VideoResult §8, jamais l'état interne) ---
    result: dict


__all__ = ["VideoState"]