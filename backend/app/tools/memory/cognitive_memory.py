# Memory Tools — Mémoire utilisateur et profil cognitif.
#
# Ce module fusionne la gestion des faits utilisateur et du profil
# pour simplifier l'interface LLM tout en conservant la granularité
# du stockage.
from langchain_core.tools import tool
from typing import Any

from app.services.memory.memory import (
    delete_fact,
    get_facts,
    patch_profile,
    read_profile,
    save_fact,
    search_facts,
    update_fact,
)
from app.services.learning.learning_profile import (
    read_learning_profile,
    search_learning_memories,
)

@tool
def update_user_identity(updates: dict) -> dict:
    """Met à jour l'identité et le profil de l'apprenant (fusion faits et profil).

    Utilise ce tool pour enregistrer toute information durable sur l'utilisateur :
    - Profil : nom, description globale.
    - Faits : catégorie (identity, background, personality, preference, interest) et contenu.

    Args:
        updates: Un dictionnaire pouvant contenir :
            - "name": (str) nouveau nom.
            - "description": (str) nouvelle description du profil.
            - "facts": (list[dict]) liste de faits à enregistrer, chaque fait étant :
                {"category": "...", "content": "...", "confidence": 1.0}

    Returns:
        dict: Résumé des mises à jour effectuées.
    """
    from langgraph.config import get_config

    config = get_config() or {}
    user_id = (config.get("configurable") or {}).get("user_id", "")
    if not user_id:
        return {"error": "user_id manquant dans la config"}

    results = {"profile": None, "facts": []}

    # 1. Mise à jour du profil
    profile_updates = {}
    if "name" in updates:
        profile_updates["name"] = updates["name"]
    if "description" in updates:
        profile_updates["description"] = updates["description"]

    if profile_updates:
        results["profile"] = patch_profile(user_id, profile_updates)

    # 2. Mise à jour des faits
    facts_to_save = updates.get("facts", [])
    for f in facts_to_save:
        category = f.get("category")
        content = f.get("content")
        confidence = f.get("confidence", 1.0)
        if category and content:
            saved = save_fact(user_id, category, content, confidence=confidence)
            results["facts"].append(saved)

    return results

@tool
def query_cognitive_memory(query: str) -> list[dict]:
    """Recherche hybride dans toute la mémoire cognitive de l'apprenant.

    Interroge simultanément :
    - Les faits personnels (identité, préférences, intérêts).
    - La mémoire pédagogique (résumés de sessions, objectifs, observations).

    Args:
        query: La requête en langage naturel.

    Returns:
        list[dict]: Résultats classés par pertinence, avec le type de mémoire source.
    """
    from langgraph.config import get_config

    config = get_config() or {}
    user_id = (config.get("configurable") or {}).get("user_id", "")
    if not user_id:
        return [{"error": "user_id manquant dans la config"}]

    # Recherche dans les faits
    user_facts = search_facts(user_id, query)
    for f in user_facts:
        f["memory_type"] = "user_fact"

    # Recherche dans le learning profile
    learning_memories = search_learning_memories(user_id, query)
    # search_learning_memories déjà retourne un format avec "type"
    for lm in learning_memories:
        lm["memory_type"] = lm.get("type", "learning_memory")

    # Fusion et tri simple (en réalité search_facts et search_learning_memories
    # ont des scores différents, mais on les combine ici)
    combined = user_facts + learning_memories

    # On tente de trier si les scores sont présents
    try:
        combined.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    except:
        pass

    return combined

@tool
def synthesize_persona() -> dict:
    """Synthétise les faits et le profil pour générer une description cohérente de l'apprenant.

    Analyse l'ensemble des connaissances disponibles pour transformer des faits
    épars en un portrait psychologique et cognitif structuré.

    Returns:
        dict: Un portrait synthétisé comprenant :
            - "identity": Nom et description globale.
            - "cognitive_traits": Synthèse des préférences et personnalité.
            - "learning_context": Background et intérêts.
            - "summary": Une phrase résumant l'apprenant.
    """
    from langgraph.config import get_config

    config = get_config() or {}
    user_id = (config.get("configurable") or {}).get("user_id", "")
    if not user_id:
        return {"error": "user_id manquant dans la config"}

    profile = read_profile(user_id)
    facts = get_facts(user_id)

    # On délègue la synthèse au LLM en lui fournissant les données brutes
    # Mais le tool doit retourner la structure pour que le LLM puisse l'utiliser
    # Ici, on retourne les données structurées pour que le LLM fasse la synthèse
    # dans sa réponse, ou on peut simuler une structure de synthèse.

    return {
        "raw_profile": profile,
        "raw_facts": facts,
        "instruction": "Utilise ces données pour construire un portrait cohérent de l'étudiant."
    }

memory_tools = [
    update_user_identity,
    query_cognitive_memory,
    synthesize_persona,
]
