# Memory tools — mémoire longue durée exposée au LLM.
#
# REFACTOR COMPLET : tous les tools utilisent désormais get_config()
# pour récupérer user_id depuis la config LangGraph (plus de paramètre
# user_id exposé au LLM).
#
# NAMESPACE : ("users", "profile", user_id)
# CLÉS : "profile" (name, description), "facts" (liste de MemoryFacts)
#
# Les nouveaux tools sont dans app/tools/memory/profile.py et facts.py.
# Ce fichier est la façade backward-compatible + nouveaux tools.
from langchain_core.tools import tool

from app.services.memory.memory import (
    delete_fact,
    get_facts,
    list_facts,
    patch_profile,
    read_profile,
    save_fact,
    search_facts,
    update_fact,
)

# Import des nouveaux tools (aliases vers les noms officiels)
from app.tools.memory.profile import get_user_profile as _get_user_profile_new
from app.tools.memory.profile import update_user_profile as _update_user_profile_new
from app.tools.memory.facts import get_learner_facts as _get_learner_facts
from app.tools.memory.facts import save_learner_fact as _save_learner_fact
from app.tools.memory.facts import update_learner_fact as _update_learner_fact


# ------------------------------------------------------------------
# PROFIL (profile.py)
# ------------------------------------------------------------------


@tool
def get_user_profile() -> dict:
    """Récupère le profil de l'apprenant (mémoire longue durée).

    Retourne un dict avec les clés "name" et "description".
    Retourne {"name": None, "description": None} si aucun profil
    n'existe encore pour cet apprenant.

    NOTE : retrieve_context charge automatiquement le profil AVANT
    chaque génération. Ce tool est utile pour drill-down ou vérification.
    """
    from langgraph.config import get_config

    config = get_config() or {}
    user_id = (config.get("configurable") or {}).get("user_id", "")
    if not user_id:
        return {"error": "user_id manquant dans la config"}

    profile = read_profile(user_id)
    return {
        "name": profile.get("name"),
        "description": profile.get("description"),
        "exists": profile.get("name") is not None or profile.get("description") is not None,
    }


@tool
def update_user_profile(
    name: str | None = None,
    description: str | None = None,
) -> dict:
    """Crée ou met à jour le profil de l'apprenant (PATCH merge).

    Ce tool fait un PATCH : seul les champs non-None sont mis à jour.
    Les champs absents ou None sont conservés tels quels.
    Le profil est partagé entre TOUS les threads de cet apprenant.

    Args:
        name: nouveau nom (optionnel, None = inchangé).
        description: nouvelle description (optionnel, None = inchangé).

    Returns:
        dict: profil après mise à jour {"name": ..., "description": ...}
    """
    from langgraph.config import get_config

    config = get_config() or {}
    user_id = (config.get("configurable") or {}).get("user_id", "")
    if not user_id:
        return {"error": "user_id manquant dans la config"}

    if name is None and description is None:
        return {"error": "Aucun champ à mettre à jour (name et description sont None)"}

    fields = {}
    if name is not None:
        fields["name"] = name
    if description is not None:
        fields["description"] = description

    result = patch_profile(user_id, fields)
    return result


# ------------------------------------------------------------------
# FAITS (aliases vers les noms officiels)
# ------------------------------------------------------------------


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
        list[dict]: liste de faits avec id, category, content, source,
        confidence, created_at, updated_at. Liste vide si aucune mémoire.

    NOTE : retrieve_context ne pré-charge PAS les faits (trop volumineux).
    """
    from langgraph.config import get_config

    config = get_config() or {}
    user_id = (config.get("configurable") or {}).get("user_id", "")
    if not user_id:
        return [{"error": "user_id manquant dans la config"}]

    return get_facts(user_id, category=category, limit=limit)


@tool
def save_learner_fact(
    category: str,
    content: str,
    confidence: float = 1.0,
) -> dict:
    """Enregistre UN nouveau fait durable sur l'apprenant.

    DÉDUPLICATION AUTOMATIQUE : si un fait similaire existe déjà
    (même catégorie, similarité ≥ 0.72), il est mis à jour.

    Args:
        category: identity | background | personality | preference | interest.
        content: le fait en une phrase courte, à la 3e personne.
        confidence: 1.0 pour une déclaration explicite (défaut).

    Returns:
        dict: fait créé ou mis à jour.
    """
    from langgraph.config import get_config

    config = get_config() or {}
    user_id = (config.get("configurable") or {}).get("user_id", "")
    if not user_id:
        return {"error": "user_id manquant dans la config"}

    return save_fact(user_id, category, content, source="user", confidence=confidence)


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
    """
    from langgraph.config import get_config

    config = get_config() or {}
    user_id = (config.get("configurable") or {}).get("user_id", "")
    if not user_id:
        return {"error": "user_id manquant dans la config"}

    if content is None and category is None and confidence is None:
        return {"error": "Aucun champ à mettre à jour"}

    return update_fact(user_id, fact_id, content=content, category=category, confidence=confidence)


@tool
def delete_user_memory(fact_id: str) -> dict:
    """Supprime UN fait précis de la mémoire, ciblé par son id.

    Args:
        fact_id: id du fait à supprimer.

    Returns:
        dict: {"deleted": fact_id}
    """
    from langchain.config import get_config

    config = get_config() or {}
    user_id = (config.get("configurable") or {}).get("user_id", "")
    if not user_id:
        return {"error": "user_id manquant dans la config"}

    return delete_fact(user_id, fact_id)


@tool
def search_user_memory(
    query: str,
    category: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Recherche les faits mémorisés pertinents pour une requête.

    Args:
        query: requête en langage naturel
            (ex: "préférences d'apprentissage").
        category: filtrer en plus par catégorie (optionnel).
        limit: nombre maximum de résultats (défaut 10).

    Returns:
        list[dict]: faits classés par pertinence.
    """
    from langgraph.config import get_config

    config = get_config() or {}
    user_id = (config.get("configurable") or {}).get("user_id", "")
    if not user_id:
        return [{"error": "user_id manquant dans la config"}]

    return search_facts(user_id, query, category=category, limit=limit)


# ------------------------------------------------------------------
# ALIASES backward-compat (noms anciens → nouveaux)
# ------------------------------------------------------------------

# Ces aliases permettent au code existant de continuer à fonctionner
# tout en utilisant les nouveaux noms officiels.
get_user_memory = get_learner_facts
save_user_memory = save_learner_fact
update_user_memory = update_learner_fact


# ------------------------------------------------------------------
# EXPORTS
# ------------------------------------------------------------------

memory_tools = [
    # Profil
    get_user_profile,
    update_user_profile,
    # Faits
    get_learner_facts,
    save_learner_fact,
    update_learner_fact,
    delete_user_memory,
    search_user_memory,
    # NB : les aliases backward-compat (get_user_memory, etc.) sont
    # les MÊMES objets tool — les lister ici enregistrerait deux
    # fois chaque tool dans all_tools (doublons au binding LLM).
]

__all__ = [
    # Officiels
    "get_user_profile",
    "update_user_profile",
    "get_learner_facts",
    "save_learner_fact",
    "update_learner_fact",
    "delete_user_memory",
    "search_user_memory",
    # Aliases backward-compat
    "get_user_memory",
    "save_user_memory",
    "update_user_memory",
    "memory_tools",
]