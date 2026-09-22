"""Repository du profil d'apprentissage (façade de ``learning_profile``)."""
from __future__ import annotations

from app.schemas.learning import (
    LearningGoal,
    LearningObservation,
    LearningProfile,
    TopicLearningState,
)
from app.services.learning import learning_profile as _learning_service


def read_learning_profile(user_id: str) -> LearningProfile | None:
    """Charge le profil d'apprentissage (None s'il n'existe pas)."""
    return _learning_service.read_learning_profile(user_id)


def write_learning_profile(profile: LearningProfile) -> LearningProfile:
    """Persiste le profil d'apprentissage fourni."""
    return _learning_service.write_learning_profile(profile)


def update_profile_from_observation(
    user_id: str,
    observation: LearningObservation,
    thread_id: str = "",
) -> LearningProfile | None:
    """Intègre une observation au profil (None si rejetée)."""
    return _learning_service.update_profile_from_observation(
        user_id, observation, thread_id=thread_id
    )


def list_observations(
    user_id: str, subject: str | None = None, topic: str | None = None
) -> list[dict]:
    """Liste l'historique des observations (filtrable par matière/sujet)."""
    return _learning_service.list_observations(
        user_id, subject=subject, topic=topic
    )


def validate_observation_targets(
    subject: str, topic: str | None = None
) -> tuple[bool, str]:
    """Vérifie que matière/sujet existent dans le registre officiel."""
    return _learning_service.validate_observation_targets(subject, topic)


def resolve_registry_topic(
    subject: str, topic: str, source: str | None = None
) -> str | None:
    """Résout un sujet libre vers un sujet valide du registre."""
    return _learning_service.resolve_registry_topic(
        subject, topic, source=source
    )


def create_learning_goal(
    user_id: str,
    subject: str,
    description: str,
    topic: str | None = None,
    thread_id: str = "",
) -> LearningGoal | None:
    """Crée un objectif d'apprentissage (None si rejeté)."""
    return _learning_service.create_learning_goal(
        user_id,
        subject,
        description,
        topic=topic,
        thread_id=thread_id,
    )


def update_learning_goal(
    user_id: str, goal_id: str, status: str, thread_id: str = ""
) -> LearningGoal | None:
    """Met à jour le statut d'un objectif (None si rejeté)."""
    return _learning_service.update_learning_goal(
        user_id, goal_id, status, thread_id=thread_id
    )


def get_topic_state(
    user_id: str, subject: str, topic: str
) -> TopicLearningState | None:
    """Retourne l'état d'un sujet précis (None si absent)."""
    return _learning_service.get_topic_state(user_id, subject, topic)


__all__ = [
    "read_learning_profile",
    "write_learning_profile",
    "update_profile_from_observation",
    "list_observations",
    "validate_observation_targets",
    "resolve_registry_topic",
    "create_learning_goal",
    "update_learning_goal",
    "get_topic_state",
]
