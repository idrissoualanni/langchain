"""Outils mémoire pour l'agent LiveKit.

Découplés de l'agent principal pour faciliter les tests et la maintenance.
"""

from __future__ import annotations

from typing import Any

from livekit.agents import RunContext, function_tool

from app.services.memory.memory import (
    list_facts,
    search_facts,
    save_fact,
    read_profile,
)


MEMORY_TOOLS = [
    "get_user_profile",
    "get_user_memory",
    "search_user_memory",
    "save_user_memory",
]


@function_tool
async def get_user_profile(
    context: RunContext,
    user_id: str,
) -> dict[str, Any]:
    """Retourne le profil longue durée de l'étudiant."""
    return read_profile(user_id)


@function_tool
async def get_user_memory(
    context: RunContext,
    user_id: str,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """Retourne les faits mémorisés de l'étudiant.

    Args:
        user_id: ID de l'utilisateur
        category: Filtrer par catégorie (identity, background, personality, preference, interest).
                  Si None, retourne toutes les catégories.
    """
    return list_facts(user_id, category=category)


@function_tool
async def search_user_memory(
    context: RunContext,
    user_id: str,
    query: str,
) -> list[dict[str, Any]]:
    """Recherche les souvenirs pertinents pour une requête."""
    return search_facts(user_id, query, limit=10)


@function_tool
async def save_user_memory(
    context: RunContext,
    user_id: str,
    category: str,
    content: str,
) -> dict[str, Any]:
    """Enregistre un fait durable explicitement déclaré par l'étudiant."""
    allowed_categories = {
        "identity",
        "background",
        "personality",
        "preference",
        "interest",
    }

    if category not in allowed_categories:
        return {
            "success": False,
            "error": f"Catégorie inconnue : {category}",
        }

    return save_fact(
        user_id,
        category,
        content,
        source="user",
    )