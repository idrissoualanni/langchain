# SHIM de compatibilité (refactor — phase migration).
from app.infrastructure.livekit.transcript import (
    persist_transcript,
    thread_id_from_metadata,
)

__all__ = ["persist_transcript", "thread_id_from_metadata"]
