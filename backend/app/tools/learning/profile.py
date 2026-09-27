# Tools learning — profil d'apprentissage (mémoire longue durée).
#
# Ces tools exposent le Learning Profile au LLM :
# - Niveau par matière et par topic (mastery)
# - Points forts / points faibles par topic
# - Objectifs d'apprentissage
#
# PRÉ-CHARGEMENT : retrieve_context charge automatiquement le profil
# AVANT chaque génération. Le LLM n'a PAS besoin d'appeler ces tools
# sauf pour drill-down ou mise à jour suite à une activité pédagogique.
from langchain_core.tools import tool

from app.services.learning.learning_profile import (
    get_topic_state,
    read_learning_profile,
)


@tool
def get_learning_profile() -> dict:
    """Récupère le profil d'apprentissage COMPLET de l'apprenant.

    Contient, par matière puis par topic : mastery (estimation
    de maîtrise 0..1), attempts, strengths, weak_points,
    last_assessed_at, confidence, ainsi que les objectifs
    d'apprentissage (goals).

    Ce profil est partagé entre TOUS les threads (mémoire cross-thread).

    Returns:
        dict: profil complet avec subjects (dict de SubjectLearningState)
        et goals (liste de LearningGoal). Retourne un profil vide
        {"subjects": {}, "goals": []} si l'apprenant n'a jamais été évalué.

    NOTE : ce tool n'a pas besoin d'être appelé explicitement —
    retrieve_context charge automatiquement le profil avant chaque
    génération. Utile pour drill-down ou vérification.
    """
    from langgraph.config import get_config

    config = get_config() or {}
    user_id = (config.get("configurable") or {}).get("user_id", "")
    if not user_id:
        return {"error": "user_id manquant dans la config"}

    profile = read_learning_profile(user_id)
    if profile is None:
        return {"subjects": {}, "goals": []}

    return profile.model_dump()


@tool
def get_learning_topic(
    subject: str,
    topic: str,
) -> dict:
    """Récupère l'état d'apprentissage d'UN topic précis.

    Retourne {mastery, attempts, strengths, weak_points,
    last_assessed_at, confidence} pour subject/topic (ids du
    Subject Registry, ex: python / functions).

    Args:
        subject: id de la matière (ex: "python", "biology").
        topic: id du topic (ex: "functions", "boucles").

    Returns:
        dict: état du topic ou {"error": "..."} si non trouvé.

    NOTE : pour récupérer PLUSIEURS concepts faibles/forts d'un coup,
    préférez get_weak_concepts ou get_strong_concepts.
    """
    from langgraph.config import get_config

    config = get_config() or {}
    user_id = (config.get("configurable") or {}).get("user_id", "")
    if not user_id:
        return {"error": "user_id manquant dans la config"}

    state = get_topic_state(user_id, subject, topic)
    if state is None:
        return {
            "subject": subject,
            "topic": topic,
            "mastery": None,
            "attempts": 0,
            "strengths": [],
            "weak_points": [],
            "last_assessed_at": None,
            "confidence": None,
        }

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


__all__ = ["get_learning_profile", "get_learning_topic"]