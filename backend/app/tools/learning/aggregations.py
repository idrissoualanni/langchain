# Tools learning — agrégations et searches complexes.
#
# Ces tools permettent :
# - get_weak_concepts / get_strong_concepts : concepts à réviser / maîtrisés
# - get_past_session_summaries : resumes des sessions passées
# - search_memories : recherche unifiée dans TOUTE la mémoire pédagogique
# - forget_memory : suppression RGPD (droit à l'oubli)
from langchain_core.tools import tool

from app.services.learning.learning_profile import (
    delete_all_learning,
    get_past_session_summaries,
    get_strong_concepts,
    get_weak_concepts,
    search_learning_memories,
)


@tool
def get_weak_concepts(
    subject: str | None = None,
    threshold: float = 0.5,
    limit: int = 10,
) -> list[dict]:
    """Récupère les concepts à réviser (mastery < threshold).

    Utilisé pour adapter les explications au niveau réel de l'apprenant
    et proposer des révisions ciblées.

    Args:
        subject: filtrer par matière (ex: "python"). None = toutes.
        threshold: seuil de mastery en dessous duquel un concept
            est considéré comme faible (défaut 0.5).
        limit: nombre maximum de concepts à retourner (défaut 10).

    Returns:
        list[dict]: liste de concepts avec subject, topic, mastery,
        attempts, weak_points, last_assessed_at, confidence.
        Liste vide si aucun concept faible.

    NOTE : ces concepts sont automatiquement chargés par
    retrieve_context AVANT chaque génération.
    """
    from langgraph.config import get_config

    config = get_config() or {}
    user_id = (config.get("configurable") or {}).get("user_id", "")
    if not user_id:
        return [{"error": "user_id manquant dans la config"}]

    concepts = get_weak_concepts(user_id, subject, threshold, limit)
    return concepts


@tool
def get_strong_concepts(
    subject: str | None = None,
    threshold: float = 0.8,
    limit: int = 10,
) -> list[dict]:
    """Récupère les concepts maîtrisés (mastery >= threshold).

    Utilisé pour valoriser les acquis de l'apprenant et éviter
    de réexpliquer ce qu'il maîtrise déjà.

    Args:
        subject: filtrer par matière (ex: "python"). None = toutes.
        threshold: seuil de mastery au-dessus duquel un concept
            est considéré comme maîtrisé (défaut 0.8).
        limit: nombre maximum de concepts à retourner (défaut 10).

    Returns:
        list[dict]: liste de concepts avec subject, topic, mastery,
        attempts, strengths, last_assessed_at, confidence.
        Liste vide si aucun concept fort.
    """
    from langgraph.config import get_config

    config = get_config() or {}
    user_id = (config.get("configurable") or {}).get("user_id", "")
    if not user_id:
        return [{"error": "user_id manquant dans la config"}]

    concepts = get_strong_concepts(user_id, subject, threshold, limit)
    return concepts


@tool
def get_past_session_summaries(
    limit: int = 3,
) -> list[dict]:
    """Récupère les résumés des sessions passées de l'apprenant.

    Utilisé pour maintenir la continuité pédagogique entre sessions
    et s'appuyer sur ce qui a été vu précédemment.

    Args:
        limit: nombre maximum de résumés à retourner (défaut 3,
            les plus récents).

    Returns:
        list[dict]: liste de résumés avec session_id, timestamp,
        topics_covered, summary, next_steps, sentiment.
        Liste vide si aucune session passée.
    """
    from langgraph.config import get_config

    config = get_config() or {}
    user_id = (config.get("configurable") or {}).get("user_id", "")
    if not user_id:
        return [{"error": "user_id manquant dans la config"}]

    summaries = get_past_session_summaries(user_id, limit)
    return summaries


@tool
def search_memories(
    query: str,
    limit: int = 5,
) -> list[dict]:
    """Recherche dans TOUTE la mémoire pédagogique de l'apprenant.

    Recherche dans : faits utilisateur, résumés de sessions,
    misconceptions, objectifs, et état d'apprentissage.

    Args:
        query: requête en langage naturel
            (ex: "préférences d'apprentissage", "sessions sur Python").
        limit: nombre maximum de résultats (défaut 5).

    Returns:
        list[dict]: résultats avec type (fact/session/misconception/goal),
        score de pertinence, et contenu structuré.
    """
    from langgraph.config import get_config

    config = get_config() or {}
    user_id = (config.get("configurable") or {}).get("user_id", "")
    if not user_id:
        return [{"error": "user_id manquant dans la config"}]

    results = search_learning_memories(user_id, query, limit)
    return results


@tool
def forget_memory(
    scope: str,
    confirm: bool = False,
) -> dict:
    """Supprime les données de l'apprenant (RGPD — droit à l'oubli).

    ATTENTION : action IRRÉVERSIBLE. Tous les'apprentissage, faits,
    sessions et objectifs de l'apprenant seront supprimés.

    Args:
        scope: "all" (toute la mémoire) ou "facts" (seulement les faits).
        confirm: doit être True pour confirmer la suppression.

    Returns:
        dict: {"deleted": True, "scope": ...} ou {"error": "..."}

    NOTE : cette fonction ne supprime PAS le thread/checkpoint.
    """
    from langgraph.config import get_config

    config = get_config() or {}
    user_id = (config.get("configurable") or {}).get("user_id", "")
    if not user_id:
        return {"error": "user_id manquant dans la config"}

    if not confirm:
        return {
            "error": (
                "Confirmation requise : forget_memory(scope='all', confirm=True). "
                "Cette action est IRRÉVERSIBLE."
            )
        }

    if scope not in ("all", "facts"):
        return {"error": "scope doit être 'all' ou 'facts'"}

    if scope == "all":
        delete_all_learning(user_id)
        from app.services.memory.memory import delete_all_facts

        delete_all_facts(user_id)
    else:
        from app.services.memory.memory import delete_all_facts

        delete_all_facts(user_id)

    from app.logging.events import log_event

    log_event(
        "MEMORY_FORGET",
        message=f"Memory deleted | user={user_id} | scope={scope}",
        user_id=user_id,
        extra={"scope": scope},
    )

    return {"deleted": True, "scope": scope}


__all__ = [
    "get_weak_concepts",
    "get_strong_concepts",
    "get_past_session_summaries",
    "search_memories",
    "forget_memory",
]