# SHIM de compatibilité (refactor — phase migration).
#
# Les contrats learning ont déménagé vers app/schemas/learning.py.
# SUPPRESSION prévue phase cleanup (§30 mission) après vérification.
from app.schemas.learning import (
    OBSERVATION_SOURCES,
    LearningContextInfo,
    LearningGoal,
    LearningObservation,
    LearningProfile,
    SubjectLearningState,
    TopicLearningState,
)

__all__ = [
    "TopicLearningState",
    "SubjectLearningState",
    "LearningGoal",
    "LearningObservation",
    "LearningProfile",
    "LearningContextInfo",
    "OBSERVATION_SOURCES",
]
