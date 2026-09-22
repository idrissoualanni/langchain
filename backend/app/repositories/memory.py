"""Repository de la mémoire longue durée (façade de ``app.services.memory``)."""
from __future__ import annotations

from app.services.memory import memory as _memory_service


# Catégories de faits exposées telles quelles (aucune redéfinition).
FACT_CATEGORIES: tuple[str, ...] = _memory_service.FACT_CATEGORIES


def get_store() -> object:
    """Retourne le singleton du store de mémoire longue durée."""
    return _memory_service.get_store()


def read_profile(user_id: str) -> dict:
    """Lit le profil (nom/description) d'un utilisateur."""
    return _memory_service.read_profile(user_id)


def write_profile(user_id: str, fields: dict, thread_id: str = "") -> dict:
    """Crée ou met à jour le profil d'un utilisateur."""
    return _memory_service.write_profile(
        user_id, fields, thread_id=thread_id
    )


def list_facts(
    user_id: str, category: str | None = None, thread_id: str = ""
) -> list[dict]:
    """Liste les faits mémoire, optionnellement filtrés par catégorie."""
    return _memory_service.list_facts(
        user_id, category=category, thread_id=thread_id
    )


def save_fact(
    user_id: str,
    category: str,
    content: str,
    source: str = "user",
    confidence: float = 1.0,
    thread_id: str = "",
) -> dict:
    """Ajoute un fait mémoire (avec déduplication côté service)."""
    return _memory_service.save_fact(
        user_id,
        category,
        content,
        source=source,
        confidence=confidence,
        thread_id=thread_id,
    )


def update_fact(
    user_id: str,
    fact_id: str,
    content: str | None = None,
    category: str | None = None,
    confidence: float | None = None,
    thread_id: str = "",
) -> dict:
    """Met à jour un fait précis désigné par son identifiant."""
    return _memory_service.update_fact(
        user_id,
        fact_id,
        content=content,
        category=category,
        confidence=confidence,
        thread_id=thread_id,
    )


def delete_fact(
    user_id: str, fact_id: str, thread_id: str = ""
) -> dict:
    """Supprime un fait précis désigné par son identifiant."""
    return _memory_service.delete_fact(
        user_id, fact_id, thread_id=thread_id
    )


def search_facts(
    user_id: str,
    query: str,
    category: str | None = None,
    limit: int = 10,
    thread_id: str = "",
) -> list[dict]:
    """Recherche les faits pertinents pour une requête donnée."""
    return _memory_service.search_facts(
        user_id,
        query,
        category=category,
        limit=limit,
        thread_id=thread_id,
    )


def read_profile_for_api(user_id: str) -> dict:
    """Lit le profil au format API (ne lève jamais)."""
    return _memory_service.read_profile_for_api(user_id)


def memory_overview_for_api(user_id: str) -> dict:
    """Retourne la vue complète (profil + faits par catégorie)."""
    return _memory_service.memory_overview_for_api(user_id)


__all__ = [
    "FACT_CATEGORIES",
    "get_store",
    "read_profile",
    "write_profile",
    "list_facts",
    "save_fact",
    "update_fact",
    "delete_fact",
    "search_facts",
    "read_profile_for_api",
    "memory_overview_for_api",
]
