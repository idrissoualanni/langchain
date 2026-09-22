# SHIM de compatibilité (refactor — phase migration).
#
# Les contrats subgraph ont déménagé vers app/schemas/workflow.py.
# SUPPRESSION prévue phase cleanup (§30 mission) après vérification.
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
    "WorkflowName",
    "JobStatus",
    "SubgraphInput",
    "SubgraphResult",
    "ProblemResult",
    "CodingResult",
    "ResearchResult",
    "VideoResult",
    "ActivityResult",
    "DocumentResult",
    "SUBGRAPH_RESULTS",
    "KNOWN_WORKFLOWS",
]
