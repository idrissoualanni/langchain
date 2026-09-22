
from langchain_core.tools import tool

from app.services.learning.learning_context import get_learning_context
from app.services.learning.learning_profile import (
    create_learning_goal,
    get_topic_state,
    read_learning_profile,
    update_learning_goal,
    update_profile_from_observation,
)
from app.schemas.learning import LearningObservation


@tool
def get_learning_profile(user_id: str) -> dict | str:
    """Récupère le profil d'apprentissage PERSISTANT de l'étudiant.

    Contient, par matière puis par topic : mastery (estimation
    de maîtrise 0..1), attempts, strengths, weak_points,
    last_assessed_at, confidence, ainsi que les objectifs
    d'apprentissage (goals). Ce profil est partagé entre TOUS les
    threads de l'étudiant (mémoire cross-thread).

    Retourne "Aucun profil d'apprentissage" si l'étudiant n'a
    encore jamais été évalué — ce n'est PAS une erreur.
    """
    profile = read_learning_profile(user_id)
    if profile is None:
        return (
            "Aucun profil d'apprentissage pour cet étudiant "
            "(jamais évalué). Commence par une activité pédagogique."
        )
    return profile.model_dump()


@tool
def get_learning_topic(
    user_id: str,
    subject: str,
    topic: str,
) -> dict | str:
    """Récupère l'état d'apprentissage d'UN topic précis.

    Retourne {mastery, attempts, strengths, weak_points,
    last_assessed_at, confidence} pour subject/topic (ids du
    Subject Registry, ex: python / functions). Utile pour
    adapter une explication au niveau réel de l'étudiant sur
    ce topic.
    """
    state = get_topic_state(user_id, subject, topic)
    if state is None:
        return (
            f"Aucune donnée d'apprentissage pour "
            f"{subject}/{topic} (topic jamais travaillé)."
        )
    return {
        "subject": subject,
        "topic": topic,
        "mastery": state.mastery,
        "attempts": state.attempts,
        "strengths": state.strengths,
        "weak_points": state.weak_points,
        "last_assessed_at": state.last_assessed_at,
        "confidence": state.confidence,
    }


@tool
def record_learning_observation(
    user_id: str,
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
        user_id: identifiant persistant de l'étudiant.
        subject: id matière du Subject Registry (ex: python).
        topic: id topic (ex: functions).
        observation_type: exercise | quiz | assessment |
            teacher_feedback.
        score: score normalisé 0..1 si l'observation est
            quantifiable (None pour un feedback qualitatif).
        strengths: points forts observés sur CE topic.
        weak_points: points faibles observés sur CE topic.
        confidence: fiabilité de l'observation (défaut 1.0).

    Le subject/topic sont VALIDÉS contre le Subject Registry :
    une matière inconnue est rejetée (pas de création implicite).
    """
    try:
        observation = LearningObservation(
            subject=subject,
            topic=topic,
            type=observation_type,  # Literal validé par pydantic
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

    profile = update_profile_from_observation(
        user_id, observation
    )
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


@tool
def update_learning_goal(
    user_id: str,
    action: str,
    subject: str,
    description: str = "",
    topic: str | None = None,
    goal_id: str | None = None,
    status: str = "active",
) -> dict | str:
    """Gère les objectifs d'apprentissage de l'étudiant.

    Args:
        user_id: identifiant persistant de l'étudiant.
        action: create | update.
        subject: id matière (Subject Registry).
        description: objectif en langage clair (create).
        topic: topic ciblé optionnel.
        goal_id: id du goal (update).
        status: active | completed | paused (update).
    """
    if action == "create":
        if not description.strip():
            return "Création de goal impossible : description vide."
        goal = create_learning_goal(
            user_id, subject, description, topic=topic
        )
        if goal is None:
            return (
                f"Goal rejeté : subject '{subject}' ou topic "
                f"'{topic}' inconnu du Subject Registry."
            )
        return goal.model_dump()

    if action == "update":
        goal = update_learning_goal(
            user_id, goal_id or "", status
        )
        if goal is None:
            return (
                f"Goal introuvable ou statut invalide "
                f"(goal_id={goal_id}, status={status})."
            )
        return goal.model_dump()

    return "Action inconnue (create | update)."


learning_tools = [
    get_learning_profile,
    get_learning_topic,
    record_learning_observation,
    update_learning_goal,
]
