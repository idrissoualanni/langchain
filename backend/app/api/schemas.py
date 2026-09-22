# SHIM de compatibilité (refactor — phase migration).
#
# Les contrats ont déménagé vers app/schemas/ (user/thread/chat/
# memory/subject/activity/document). Ce module ré-exporte pour les
# consommateurs externes encore sur l'ancien chemin.
# SUPPRESSION prévue phase cleanup (§30 mission) après vérification :
# no imports + no registration + no route + no tests + no runtime.
from app.schemas.activity import (
    ActivityLogEntryOut,
    ActivitySummary,
    CodeRunRequest,
    CodeRunResponse,
    ThreadActivityResponse,
)
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.document import (
    DocumentOut,
    DocumentSearchResponseOut,
    DocumentUploadCreate,
)
from app.schemas.health import HealthResponse
from app.schemas.memory import (
    MemoryFactCreate,
    MemoryFactOut,
    MemoryFactUpdate,
    MemoryOverviewOut,
)
from app.schemas.subject import (
    ContextPreviewRequest,
    ContextPreviewResponse,
    SubjectOut,
    TopicOut,
)
from app.schemas.thread import (
    CheckpointOut,
    MessageOut,
    StateResponse,
    ThreadCreate,
    ThreadOut,
    ThreadRename,
)
from app.schemas.user import (
    ProfileOut,
    ProfileUpdate,
    UserCreate,
    UserOut,
)

__all__ = [
    "UserCreate",
    "UserOut",
    "ThreadCreate",
    "ThreadOut",
    "ThreadRename",
    "ChatRequest",
    "ChatResponse",
    "MessageOut",
    "StateResponse",
    "CheckpointOut",
    "HealthResponse",
    "ProfileOut",
    "ProfileUpdate",
    "MemoryFactOut",
    "MemoryOverviewOut",
    "MemoryFactCreate",
    "MemoryFactUpdate",
    "SubjectOut",
    "TopicOut",
    "ContextPreviewRequest",
    "ContextPreviewResponse",
    "ActivitySummary",
    "ActivityLogEntryOut",
    "ThreadActivityResponse",
    "CodeRunRequest",
    "CodeRunResponse",
    "DocumentUploadCreate",
    "DocumentOut",
    "DocumentSearchResponseOut",
]
