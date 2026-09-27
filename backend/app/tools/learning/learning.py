# Tools learning — façade regroupant TOUS les tools pédagogiques.
#
# REFACTOR COMPLET : ce fichier est la façade qui exporte tous les tools
# learning. Les tools sont définis dans des modules séparés :
#   - profile.py   : get_learning_profile, get_learning_topic
#   - goals.py     : create_learning_goal, update_goal_progress, complete_learning_goal
#   - aggregations.py : get_weak_concepts, get_strong_concepts,
#                       get_past_session_summaries, search_memories, forget_memory
#   - session.py   : save_session_summary
#
# record_learning_observation reste ici (défini dans learning.py original).
from langchain_core.tools import tool

from app.services.learning.learning_profile import (
    update_profile_from_observation,
)
from app.schemas.learning import LearningObservation

# Imports des nouveaux modules
from app.tools.learning.profile import get_learning_profile, get_learning_topic
from app.tools.learning.goals import (
    create_learning_goal,
    update_goal_progress,
    complete_learning_goal,
)
from app.tools.learning.aggregations import (
    forget_memory,
    get_past_session_summaries,
    get_strong_concepts,
    get_weak_concepts,
    search_memories,
)
from app.tools.learning.session import save_session_summary


# ------------------------------------------------------------------
# record_learning_observation (original, conservé)
# ------------------------------------------------------------------


@tool
def record_learning_observation(
    subject: str,
    topic: str,
    observation_type: str,
    score: float | None = None,
    strengths: list[str] | None = None,
    weak_points: list[str] | None = None,
    confidence: float = 1.0,
) -> dict | str:
    """Enregistre une observation pédagogique SIGNIFICATIVE.

    À utiliser UNIQUEMENT après un événement pédagogique réel :
    évaluation d'exercice (evaluate_answer), quiz, assessment ou
    correction. Ne JAMAIS enregistrer d'observation pour un
    message ordinaire de conversation.

    Args:
        subject: id matière du Subject Registry (ex: python).
        topic: id topic (ex: functions).
        observation_type: exercise | quiz | assessment |
            teacher_feedback.
        score: score normalisé 0..1 si quantifiable (None pour
            feedback qualitatif).
        strengths: points forts observés sur CE topic.
        weak_points: points faibles observés sur CE topic.
        confidence: fiabilité de l'observation (défaut 1.0).

    Returns:
        dict | str: état du topic après intégration, ou message d'erreur.

    NOTE : le subject/topic sont VALIDÉS contre le Subject Registry —
    une matière inconnue est rejetée (pas de création implicite).
    """
    from langgraph.config import get_config

    config = get_config() or {}
    user_id = (config.get("configurable") or {}).get("user_id", "")
    if not user_id:
        return {"error": "user_id manquant dans la config"}

    try:
        observation = LearningObservation(
            subject=subject,
            topic=topic,
            type=observation_type,
            score=score,
            strengths=strengths or [],
            weak_points=weak_points or [],
            confidence=confidence,
        )
    except Exception as exc:
        return (
            f"Observation invalide : {exc}. Types acceptés : "
            "exercise, quiz, assessment, teacher_feedback ; "
            "score/confidence dans [0..1]."
        )

    profile = update_profile_from_observation(user_id, observation)
    if profile is None:
        return (
            f"Observation rejetée : subject '{subject}' ou topic "
            f"'{topic}' inconnu du Subject Registry."
        )

    state = profile.subjects[subject].topics[topic]
    return {
        "recorded": True,
        "subject": subject,
        "topic": topic,
        "mastery": state.mastery,
        "attempts": state.attempts,
        "confidence": state.confidence,
        "weak_points": state.weak_points,
    }


# ------------------------------------------------------------------
# EXPORTS
# ------------------------------------------------------------------

learning_tools = [
    # Profile
    get_learning_profile,
    get_learning_topic,
    # Observation
    record_learning_observation,
    # Goals
    create_learning_goal,
    update_goal_progress,
    complete_learning_goal,
    # Aggregations
    get_weak_concepts,
    get_strong_concepts,
    get_past_session_summaries,
    search_memories,
    forget_memory,
    # Session
    save_session_summary,
]

__all__ = [
    # Profile
    "get_learning_profile",
    "get_learning_topic",
    # Observation
    "record_learning_observation",
    # Goals
    "create_learning_goal",
    "update_goal_progress",
    "complete_learning_goal",
    # Aggregations
    "get_weak_concepts",
    "get_strong_concepts",
    "get_past_session_summaries",
    "search_memories",
    "forget_memory",
    # Session
    "save_session_summary",
    # Liste complète
    "learning_tools",
]