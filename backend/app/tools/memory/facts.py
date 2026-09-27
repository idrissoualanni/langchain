# Tools mémoire — faits utilisateur (mémoire longue durée).
#
# Ces tools exposent les MemoryFacts au LLM. Les faits sont stockés
# sous namespace ("users", "profile", user_id), clé "facts".
#
# Catégories : identity, background, personality, preference, interest
#
# DÉDUPLICATION : save_learner_fact fait une déduplication automatique
# par similarité (seuil 0.72) — pas de doublons possibles.
from langchain_core.tools import tool

from app.services.memory.memory import (
    get_facts,
    list_facts,
    save_fact,
    search_facts,
    update_fact,
)
from app.services.memory.memory import FACT_CATEGORIES


@tool
def get_learner_facts(
    category: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Liste les faits mémorisés de l'apprenant (mémoire longue durée).

    Args:
        category: filtrer par catégorie parmi
            identity, background, personality, preference, interest.
            None = toutes les catégories.
        limit: nombre maximum de faits à retourner (défaut 50).

    Returns:
        list[dict]: liste de faits avec clés id, category, content,
        source, confidence, created_at, updated_at. Liste vide si
        aucune mémoire.

    NOTE : retrieve_context NE pré-charge PAS les faits (trop volumineux).
    Appeler ce tool pour récupérer les préférences/données utilisateur.
    """
    from langgraph.config import get_config

    config = get_config() or {}
    user_id = (config.get("configurable") or {}).get("user_id", "")
    if not user_id:
        return [{"error": "user_id manquant dans la config"}]

    facts = get_facts(user_id, category=category, limit=limit)
    return facts


@tool
def save_learner_fact(
    category: str,
    content: str,
    confidence: float = 1.0,
) -> dict:
    """Enregistre UN nouveau fait durable sur l'apprenant.

    À utiliser UNIQUEMENT quand l'apprenant declare explicitement
    une information durable sur lui-même (nom, formation, préférence
    d'apprentissage, centre d'intérêt, trait de caractère).
    Ne jamais enregistrer une question, un calcul ou une demande
    ponctuelle.

    DÉDUPLICATION AUTOMATIQUE : si un fait similaire existe déjà
    (même catégorie, similarité ≥ 0.72), il est mis à jour au lieu
    d'être créé en double.

    Args:
        category: identity | background | personality |
            preference | interest.
        content: le fait en une phrase courte, à la 3e personne
            (ex: "Étudiant en mécatronique",
            "Préfère les explications avec des exemples").
        confidence: 1.0 pour une déclaration explicite de
            l'apprenant (défaut), moins si déduit.

    Returns:
        dict: fait créé ou mis à jour avec id, category, content,
        source, confidence, created_at, updated_at.
    """
    from langgraph.config import get_config

    config = get_config() or {}
    user_id = (config.get("configurable") or {}).get("user_id", "")
    if not user_id:
        return {"error": "user_id manquant dans la config"}

    result = save_fact(
        user_id,
        category,
        content,
        source="user",
        confidence=confidence,
    )
    return result


@tool
def update_learner_fact(
    fact_id: str,
    content: str | None = None,
    category: str | None = None,
    confidence: float | None = None,
) -> dict:
    """Modifie UN fait précis de la mémoire, ciblé par son id.

    Args:
        fact_id: id du fait à modifier.
        content: nouveau contenu (None = inchangé).
        category: nouvelle catégorie (None = inchangée).
        confidence: nouvelle confiance (None = inchangée).

    Returns:
        dict: fait mis à jour.

    NOTE : ne modifie QUE ce fait — les autres restent intacts.
    """
    from langgraph.config import get_config

    config = get_config() or {}
    user_id = (config.get("configurable") or {}).get("user_id", "")
    if not user_id:
        return {"error": "user_id manquant dans la config"}

    if content is None and category is None and confidence is None:
        return {"error": "Aucun champ à mettre à jour"}

    result = update_fact(
        user_id,
        fact_id,
        content=content,
        category=category,
        confidence=confidence,
    )
    return result


__all__ = ["get_learner_facts", "save_learner_fact", "update_learner_fact"]