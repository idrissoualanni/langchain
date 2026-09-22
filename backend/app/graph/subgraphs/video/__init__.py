# VideoSubgraph (§28) — ingestion vidéo hors chemin conversationnel.
#
# Pipeline : START → validate_upload → ingest (↺ retry borné) →
# segment (↺ retry borné) → enrich → index/persist → finalize → END.
# Sortie : VideoResult (§8). Autonome, déterministe, hors-ligne.
#
# NB : les services `video_ingest.py` / `video_segment.py` décrits par
# le plan sont ABSENTS du dépôt à l'audit ; leur logique métier vit ici
# (ingest.py / segment.py) et peut être déléguée vers les fichiers
# originaux dès qu'ils existent (interface identique, wrappers fins).
from app.graph.subgraphs.video.ingest import (
    VideoFatalError,
    VideoIngestError,
    VideoTransientError,
    ingest_video,
    locate_source,
    reset_services,
    use_services,
)
from app.graph.subgraphs.video.nodes import (
    MAX_ATTEMPTS_DEFAULT,
    compile_video_subgraph,
    run_video_subgraph,
)
from app.graph.subgraphs.video.persist import VideoKnowledgeStore
from app.graph.subgraphs.video.retrieval import (
    get_video,
    get_video_segments,
    search_video_segments,
)
from app.schemas.video import (
    PedagogicalSegment,
    VideoMetadata,
    VideoUploadPayload,
)
from app.graph.subgraphs.video.segment import (
    SegmentationError,
    segment_transcript,
)
from app.graph.subgraphs.video.state import VideoState

__all__ = [
    "MAX_ATTEMPTS_DEFAULT",
    "PedagogicalSegment",
    "SegmentationError",
    "VideoFatalError",
    "VideoIngestError",
    "VideoKnowledgeStore",
    "VideoMetadata",
    "VideoState",
    "VideoTransientError",
    "VideoUploadPayload",
    "compile_video_subgraph",
    "get_video",
    "get_video_segments",
    "ingest_video",
    "locate_source",
    "reset_services",
    "run_video_subgraph",
    "search_video_segments",
    "segment_transcript",
    "use_services",
]