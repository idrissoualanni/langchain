# Tools learning — objectifs d'apprentissage.
#
# Séparation en 3 tools distincts pour lever l'ambiguïté :
# - create_learning_goal : créer un nouvel objectif
# - update_goal_progress : mettre à jour le statut d'un objectif
# - complete_learning_goal : marquer un objectif comme complété
from langchain_core.tools import tool

from app.services.learning.learning_profile import (
    create_learning_goal,
    update_learning_goal,
)
from app.schemas.learning import LearningGoal


@tool
def create_learning_goal(
    subject: str,
    description: str,
    topic: str | None = None,
) -> dict:
    """Crée un nouvel objectif d'apprentissage.

    Args:
        subject: id de la matière (Subject Registry, ex: "python").
        description: objectif en langage clair (ex:
            "Maîtriser les fonctions récursives").
        topic: topic ciblé optionnel (ex: "functions").

    Returns:
        dict: objectif créé avec id, subject, topic, description,
        status="active", created_at. Retourne {"error": "..."} si
        le subject/topic est inconnu du Registry.

    NOTE : un objectif peut être actif même si mastery est basse,
    et réciproquement.
    """
    from langgraph.config import get_config

    config = get_config() or {}
    user_id = (config.get("configurable") or {}).get("user_id", "")
    if not user_id:
        return {"error": "user_id manquant dans la config"}

    if not description.strip():
        return {"error": "La description ne peut pas être vide"}

    goal = create_learning_goal(user_id, subject, description, topic=topic)
    if goal is None:
        return {
            "error": (
                f"Subject '{subject}' ou topic '{topic}' inconnu "
                "du Subject Registry"
            )
        }
    return goal.model_dump()


@tool
def update_goal_progress(
    goal_id: str,
    status: str,
) -> dict:
    """Met à jour le statut d'un objectif d'apprentissage.

    Args:
        goal_id: identifiant de l'objectif (retourné par create_learning_goal).
        status: nouveau statut — "active" (en cours),
            "paused" (en pause).

    Returns:
        dict: objectif mis à jour. Retourne {"error": "..."} si
        goal_id introuvable ou statut invalide.

    NOTE : pour marquer un objectif comme TERMINÉ, utilisez
    complete_learning_goal (plus appropriate).
    """
    from langgraph.config import get_config

    config = get_config() or {}
    user_id = (config.get("configurable") or {}).get("user_id", "")
    if not user_id:
        return {"error": "user_id manquant dans la config"}

    if status not in ("active", "paused"):
        return {"error": "Statut invalide (active ou paused)"}

    goal = update_learning_goal(user_id, goal_id, status)
    if goal is None:
        return {"error": f"Objectif '{goal_id}' introuvable"}
    return goal.model_dump()


@tool
def complete_learning_goal(
    goal_id: str,
) -> dict:
    """Marque un objectif d'apprentissage comme-Terminé (completed).

    Args:
        goal_id: identifiant de l'objectif (retourné par create_learning_goal).

    Returns:
        dict: objectif marqué completed. Retourne {"error": "..."}
        si goal_id introuvable.
    """
    from langgraph.config import get_config

    config = get_config() or {}
    user_id = (config.get("configurable") or {}).get("user_id", "")
    if not user_id:
        return {"error": "user_id manquant dans la config"}

    goal = update_learning_goal(user_id, goal_id, "completed")
    if goal is None:
        return {"error": f"Objectif '{goal_id}' introuvable"}
    return goal.model_dump()


__all__ = [
    "create_learning_goal",
    "update_goal_progress",
    "complete_learning_goal",
]