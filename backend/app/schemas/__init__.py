# Schemas centralisés — contrats de données du backend.
#
# ARCHITECTURE (§14 mission refactor) :
#   app/schemas/ = TOUS les contrats Pydantic/dataclass/TypedDict.
#
#   - response.py  : AgentResponse (contrat central backend↔frontend §21)
#   - workflow.py  : WorkflowName/JobStatus/SubgraphInput/SubgraphResult
#                    + *Result par workflow (Problem/Coding/Research/
#                    Video/Activity/Document)
#   - context.py   : RoutingResult/Search*/Knowledge*/BuiltContext/...
#   - learning.py  : LearningProfile/Observation/Goal/ContextInfo
#   - activity.py  : état TypedDict + contrat + vues API + ActivityResult
#   - document.py  : contrats RAG + vues API documents
#   - problem.py   : domaine résolution d'énoncés (parser/plan/éval)
#   - video.py     : domaine ingestion vidéo (segments/métadonnées)
#   - subject.py   : SubjectConfig/TopicConfig + vues API matières
#   - chat.py      : ChatRequest/ChatResponse (contrat /api/chat)
#   - thread.py    : threads + état/checkpoints (contrats /api/threads)
#   - user.py      : utilisateurs + profils (contrats /api/users)
#   - memory.py    : MemoryFacts (contrats mémoire longue durée)
#   - common.py    : helpers partagés (validation UUID, horodatage UTC)
#
# RÈGLE : les schemas sont des FEUILLES — ils n'importent jamais de
# logique métier (services/graph/api). Seuls imports autorisés :
# stdlib, pydantic, et autres modules app.schemas.
from app.schemas.activity import (
    ACTIVITY_ABANDONED,
    ACTIVITY_CHECKING_UNDERSTANDING,
    ACTIVITY_COMPLETED,
    ACTIVITY_EVALUATING,
    ACTIVITY_GIVING_HINT,
    ACTIVITY_IDLE,
    ACTIVITY_TYPES,
    ACTIVITY_TYPE_EXERCISE,
    ACTIVITY_TYPE_QUIZ,
    ACTIVITY_TYPE_UNDERSTANDING_CHECK,
    ACTIVITY_WAITING_ANSWER,
    ACTIVITY_WAITING_RETRY,
    ALL_ACTIVITY_STATUSES,
    ALL_RESPONSE_TYPES,
    CONTINUABLE_STATUSES,
    TERMINAL_STATUSES,
    ActivityContract,
    ActivityLogEntry,
    ActivityLogEntryOut,
    ActivitySummary,
    CodeRunRequest,
    CodeRunResponse,
    LearningActivityState,
    QuizState,
    ThreadActivityResponse,
    activity_to_contract,
    lifecycle_stage,
    make_result,
    new_activity_id,
    summarize_activity,
)
from app.schemas.budget import (
    BudgetResult,
    BudgetSection,
    BudgetStatus,
    ContextBudget,
    apply_budget,
    build_budget,
    estimate_tokens,
)
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.common import utc_now, valid_uuid
from app.schemas.context import (
    ActivityContextInfo,
    AgentContext,
    BuiltContext,
    ContextStats,
    DocumentContextInfo,
    FallbackDecision,
    KnowledgeResult,
    KnowledgeSearchResult,
    ResolvedTools,
    RoutingResult,
    SearchResponse,
    SearchResult,
    SubjectContextInfo,
    ThreadContextInfo,
    UserContextInfo,
)
from app.schemas.document import (
    ALLOWED_EXTENSIONS,
    DOCUMENT_SEARCH_STATUS,
    DocumentChunk,
    DocumentOut,
    DocumentRecord,
    DocumentSearchResponse,
    DocumentSearchResponseOut,
    DocumentSearchResult,
    DocumentUploadCreate,
)
from app.schemas.health import HealthResponse
from app.schemas.learning import (
    OBSERVATION_SOURCES,
    LearningContextInfo,
    LearningGoal,
    LearningObservation,
    LearningProfile,
    SubjectLearningState,
    TopicLearningState,
)
from app.schemas.memory import (
    MemoryFactCreate,
    MemoryFactOut,
    MemoryFactUpdate,
    MemoryOverviewOut,
)
from app.schemas.model_capabilities import (
    ModelCapabilities,
    get_model_capabilities,
    list_configured_models,
    supports,
)
from app.schemas.problem import (
    ErrorKind,
    ParsedStatement,
    RigorScore,
    SolutionStep,
    StatementClass,
    StepEvaluation,
    StepVerdict,
)
from app.schemas.response import (
    AgentResponse,
    AgentResponseStatus,
    AgentResponseType,
)
from app.schemas.subject import (
    ContextPreviewRequest,
    ContextPreviewResponse,
    SubjectConfig,
    SubjectOut,
    TopicConfig,
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
from app.schemas.video import (
    PedagogicalSegment,
    VideoMetadata,
    VideoUploadPayload,
)
from app.schemas.workflow import (
    KNOWN_WORKFLOWS,
    SUBGRAPH_RESULTS,
    ActivityResult,
    CodingResult,
    DocumentResult,
    JobStatus,
    ProblemResult,
    ResearchResult,
    SubgraphInput,
    SubgraphResult,
    VideoResult,
    WorkflowName,
)

__all__ = [
    "ACTIVITY_ABANDONED",
    "ACTIVITY_CHECKING_UNDERSTANDING",
    "ACTIVITY_COMPLETED",
    "ACTIVITY_EVALUATING",
    "ACTIVITY_GIVING_HINT",
    "ACTIVITY_IDLE",
    "ACTIVITY_TYPES",
    "ACTIVITY_TYPE_EXERCISE",
    "ACTIVITY_TYPE_QUIZ",
    "ACTIVITY_TYPE_UNDERSTANDING_CHECK",
    "ACTIVITY_WAITING_ANSWER",
    "ACTIVITY_WAITING_RETRY",
    "ALL_ACTIVITY_STATUSES",
    "ALL_RESPONSE_TYPES",
    "ALLOWED_EXTENSIONS",
    "AgentContext",
    "AgentResponse",
    "AgentResponseStatus",
    "AgentResponseType",
    "ActivityContextInfo",
    "ActivityContract",
    "ActivityLogEntry",
    "ActivityLogEntryOut",
    "ActivityResult",
    "ActivitySummary",
    "BuiltContext",
    "BudgetResult",
    "BudgetSection",
    "BudgetStatus",
    "CONTINUABLE_STATUSES",
    "TERMINAL_STATUSES",
    "ChatRequest",
    "ChatResponse",
    "CheckpointOut",
    "CodeRunRequest",
    "CodeRunResponse",
    "ContextPreviewRequest",
    "ContextPreviewResponse",
    "ContextStats",
    "ContextBudget",
    "CodingResult",
    "DOCUMENT_SEARCH_STATUS",
    "DocumentChunk",
    "DocumentContextInfo",
    "DocumentOut",
    "DocumentRecord",
    "DocumentResult",
    "DocumentSearchResponse",
    "DocumentSearchResponseOut",
    "DocumentSearchResult",
    "DocumentUploadCreate",
    "ErrorKind",
    "FallbackDecision",
    "HealthResponse",
    "KNOWN_WORKFLOWS",
    "JobStatus",
    "KnowledgeResult",
    "KnowledgeSearchResult",
    "LearningActivityState",
    "LearningContextInfo",
    "LearningGoal",
    "LearningObservation",
    "LearningProfile",
    "MemoryFactCreate",
    "MemoryFactOut",
    "MemoryFactUpdate",
    "MemoryOverviewOut",
    "MessageOut",
    "ModelCapabilities",
    "OBSERVATION_SOURCES",
    "ParsedStatement",
    "PedagogicalSegment",
    "ProblemResult",
    "ProfileOut",
    "ProfileUpdate",
    "QuizState",
    "ResearchResult",
    "ResolvedTools",
    "RigorScore",
    "RoutingResult",
    "SearchResponse",
    "SearchResult",
    "SolutionStep",
    "StateResponse",
    "StatementClass",
    "StepEvaluation",
    "StepVerdict",
    "SUBGRAPH_RESULTS",
    "SubgraphInput",
    "SubgraphResult",
    "SubjectConfig",
    "SubjectContextInfo",
    "SubjectLearningState",
    "SubjectOut",
    "TERMINAL_STATUSES",
    "ThreadActivityResponse",
    "ThreadContextInfo",
    "ThreadCreate",
    "ThreadOut",
    "ThreadRename",
    "TopicConfig",
    "TopicLearningState",
    "TopicOut",
    "UserContextInfo",
    "UserCreate",
    "UserOut",
    "VideoMetadata",
    "VideoResult",
    "VideoUploadPayload",
    "WorkflowName",
    "activity_to_contract",
    "apply_budget",
    "build_budget",
    "estimate_tokens",
    "get_model_capabilities",
    "lifecycle_stage",
    "list_configured_models",
    "make_result",
    "new_activity_id",
    "summarize_activity",
    "supports",
    "utc_now",
    "valid_uuid",
]
