# SHIM de compatibilité (refactor — phase migration).
#
# Les schémas du domaine Video ont déménagé vers
# app/schemas/video.py. SUPPRESSION prévue phase cleanup (§30).
from app.schemas.video import (
    PedagogicalSegment,
    VideoMetadata,
    VideoUploadPayload,
)

__all__ = [
    "PedagogicalSegment",
    "VideoMetadata",
    "VideoUploadPayload",
]
