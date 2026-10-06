# Tools mémoire — profil utilisateur (mémoire longue durée).
#
# Ces tools exposent le profil utilisateur (name/description) au LLM.
# Ils lisent/écrivent dans le store LangGraph (PostgresStore/Neon
# ou SqliteStore local) sous namespace ("users", "profile", user_id).
#
# PRÉ-CHARGEMENT : retrieve_context (node graph) charge automatiquement
# le profil AVANT chaque génération — le LLM n'a PAS besoin d'appeler
# ces tools sauf pour drill-down ou mise à jour explicite.
from langchain_core.tools import tool

from app.services.memory.memory import write_profile, read_profile


@tool
def get_user_profile() -> dict:
    """Récupère le profil de l'apprenant (mémoire longue durée).

    Retourne un dict avec les clés "name" et "description".
    Retourne {"name": None, "description": None} si aucun profil
    n'existe encore pour cet apprenant.

    NOTE : ce tool n'a pas besoin d'être appelé explicitement —
    retrieve_context charge automatiquement le profil avant chaque
    génération. Utile pour drill-down ou vérification.

    Returns:
        dict: {"name": str | None, "description": str | None}
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

    NOTE : appeler ce tool quand l'apprenant indique une préférence,
    un changement de contexte, ou toute information durable sur lui.
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

    result = write_profile(user_id, fields)
    return result


__all__ = ["get_user_profile", "update_user_profile"]