import logging
import threading
from datetime import datetime, timezone
from typing import Any

from app.config import log_safe
from app.logging.events import log_event

# Lazy import inside functions to break circular dependency with app.services.context.builder
# and app.services.memory.cognitive_store

logger = logging.getLogger(__name__)

# Nous conservons les constantes pour la rétro-compatibilité des logs et schémas,
# mais la logique interne est désormais déléguée au CognitiveStore et HybridRetriever.
FACT_CATEGORIES = (
    "identity",
    "background",
    "personality",
    "preference",
    "interest",
)

FACT_SOURCES = ("user", "inferred", "system", "teacher")

_store_lock = threading.RLock()

def _now() -> str:
    """Timestamp ISO 8601 UTC."""
    return datetime.now(timezone.utc).isoformat()

def _current_thread_id() -> str:
    """thread_id courant depuis la config LangGraph (si disponible)."""
    try:
        from langgraph.config import get_config
        cfg = get_config() or {}
        return (cfg.get("configurable") or {}).get("thread_id", "")
    except Exception:
        return ""

# ------------------------------------------------------------------
# Accesseurs (Rétro-compatibilité)
# ------------------------------------------------------------------

def get_facts(user_id: str, category: str | None = None, limit: int = 100) -> list[dict]:
    """Alias pour list_facts pour la rétro-compatibilité."""
    return list_facts(user_id, category=category, limit=limit)

def get_store():
    """Retourne le store cognitif (singleton)."""
    from app.services.memory.cognitive_store import cognitive_store
    return cognitive_store

def read_profile_for_api(user_id: str) -> dict:
    """Version de read_profile pour l'API (sécurisée)."""
    return read_profile(user_id)

def update_fact(user_id: str, fact_id: str, content: str, thread_id: str = "") -> dict:
    """Met à jour un fait existant via le CognitiveStore."""
    from app.services.memory.cognitive_store import cognitive_store
    try:
        if hasattr(cognitive_store, "update_memory"):
            cognitive_store.update_memory(user_id, fact_id, content)
        else:
            # Fallback delete + save
            if hasattr(cognitive_store, "delete_memory"):
                cognitive_store.delete_memory(user_id, fact_id)
            cognitive_store.save_memory(user_id, content)

        return {"updated": fact_id, "content": content}
    except Exception as exc:
        log_event("MEMORY_UPDATE_ERROR", level="ERROR", message=f"Update failed: {exc}", user_id=user_id)
        raise

def patch_profile(user_id: str, fields: dict, thread_id: str = "") -> dict:
    """Met à jour partiellement le profil utilisateur via le CognitiveStore."""
    return write_profile(user_id, fields, thread_id)

# ------------------------------------------------------------------
# Profil v2 (Délégué au CognitiveStore)
# ------------------------------------------------------------------

def read_profile(user_id: str) -> dict:
    """Lit le profil utilisateur depuis le CognitiveStore.

    Retourne {"name": ..., "description": ...}.
    """
    from app.services.memory.cognitive_store import cognitive_store
    thread_id = _current_thread_id()
    try:
        # On récupère le profil via une recherche sémantique ciblée sur le type 'profile'
        memories = cognitive_store.retrieve_memories(
            user_id=user_id,
            query="profil utilisateur nom description",
            limit=1
        )

        profile = {"name": None, "description": None}
        if memories:
            # On extrait les infos du premier résultat pertinent
            meta = memories[0].get("metadata", {})
            if meta.get("type") == "profile":
                profile = {
                    "name": meta.get("name"),
                    "description": meta.get("description")
                }

        log_event(
            "MEMORY_READ",
            message=f"Profile read via CognitiveStore | user={user_id}",
            user_id=user_id,
            thread_id=thread_id,
        )
        return profile
    except Exception as exc:
        log_event("MEMORY_READ_ERROR", level="ERROR", message=f"Profile read failed: {exc}", user_id=user_id)
        raise

def write_profile(user_id: str, fields: dict, thread_id: str = "") -> dict:
    """Met à jour le profil utilisateur via le CognitiveStore."""
    from app.services.memory.cognitive_store import cognitive_store
    if thread_id == "":
        thread_id = _current_thread_id()

    try:
        # On enregistre le profil comme un souvenir spécial de type 'identity'
        # pour qu'il soit indexé vectoriellement tout en restant identifiable via metadata
        content = f"Profil utilisateur : {fields.get('name', '')} - {fields.get('description', '')}"
        cognitive_store.save_memory(
            user_id=user_id,
            content=content,
            memory_type="identity",
            metadata={"type": "profile", **fields}
        )

        log_event(
            "MEMORY_WRITE",
            message=f"Profile written to CognitiveStore | user={user_id}",
            user_id=user_id,
            thread_id=thread_id,
        )
        return fields
    except Exception as exc:
        log_event("MEMORY_WRITE_ERROR", level="ERROR", message=f"Profile write failed: {exc}", user_id=user_id)
        raise

# ------------------------------------------------------------------
# MemoryFacts (Entièrement basculés sur Neon/CognitiveStore)
# ------------------------------------------------------------------

def save_fact(
    user_id: str,
    category: str,
    content: str,
    source: str = "user",
    confidence: float = 1.0,
    thread_id: str = "",
) -> dict:
    """Ajoute un fait via le CognitiveStore (Gestion Neon native)."""
    from app.services.memory.cognitive_store import cognitive_store
    if thread_id == "":
        thread_id = _current_thread_id()

    try:
        # Le CognitiveStore gère l'embedding et l'insertion Neon
        memory_id = cognitive_store.save_memory(
            user_id=user_id,
            content=content,
            memory_type=category,
            metadata={"source": source, "confidence": confidence}
        )

        log_event(
            "MEMORY_WRITE",
            message=f"Fact saved to Neon | user={user_id} | cat={category}",
            user_id=user_id,
            thread_id=thread_id,
            extra={"memory_id": memory_id, "category": category}
        )
        return {"id": memory_id, "content": content, "category": category}
    except Exception as exc:
        log_event("MEMORY_WRITE_ERROR", level="ERROR", message=f"Fact save failed: {exc}", user_id=user_id)
        raise

def search_facts(
    user_id: str,
    query: str,
    category: str | None = None,
    limit: int = 10,
    thread_id: str = "",
) -> list[dict]:
    """Recherche hybride (Sémantique + Lexical) via le HybridRetriever."""
    from app.services.memory.hybrid_retriever import default_hybrid_retriever
    if thread_id == "":
        thread_id = _current_thread_id()

    try:
        # Utilisation du nouveau moteur de recherche "Sens Réel"
        results = default_hybrid_retriever.retrieve(
            user_id=user_id,
            query=query,
            limit=limit
        )

        # Filtrage par catégorie si demandé
        if category:
            results = [r for r in results if r.get("type") == category]

        log_event(
            "MEMORY_SEARCH",
            message=f"Hybrid search Neon | user={user_id} | results={len(results)}",
            user_id=user_id,
            thread_id=thread_id,
            extra={"query": query[:100], "results": len(results)}
        )
        return results
    except Exception as exc:
        log_event("MEMORY_SEARCH_ERROR", level="ERROR", message=f"Search failed: {exc}", user_id=user_id)
        raise

def list_facts(user_id: str, category: str | None = None, thread_id: str = "", limit: int = 100) -> list[dict]:
    """Liste les faits depuis Neon (via recherche sémantique large)."""
    from app.services.memory.cognitive_store import cognitive_store
    if thread_id == "":
        thread_id = _current_thread_id()

    try:
        # On utilise le CognitiveStore pour récupérer les souvenirs sans filtre de requête spécifique
        facts = cognitive_store.retrieve_memories(user_id=user_id, query="", limit=limit)
        if category:
            facts = [f for f in facts if f.get("type") == category]
        return facts
    except Exception as exc:
        log_event("MEMORY_READ_ERROR", level="ERROR", message=f"List facts failed: {exc}", user_id=user_id)
        return []

def delete_fact(user_id: str, fact_id: str, thread_id: str = "") -> dict:
    """Supprime un fait dans Neon via le CognitiveStore."""
    from app.services.memory.cognitive_store import cognitive_store
    try:
        # On suppose que delete_memory sera implémenté dans CognitiveStore
        if hasattr(cognitive_store, "delete_memory"):
            cognitive_store.delete_memory(user_id, fact_id)
        else:
            logger.warning("delete_memory not yet implemented in CognitiveStore")

        return {"deleted": fact_id}
    except Exception as exc:
        log_event("MEMORY_DELETE_ERROR", level="ERROR", message=f"Delete failed: {exc}", user_id=user_id)
        raise

def memory_overview_for_api(user_id: str) -> dict:
    """Vue complète pour le frontend utilisant le moteur cognitif."""
    try:
        profile = read_profile(user_id)
        facts = list_facts(user_id)

        by_category = {cat: [] for cat in FACT_CATEGORIES}
        for f in facts:
            cat = f.get("type")
            if cat in by_category:
                by_category[cat].append(f)

        return {
            "user_id": user_id,
            "identity": profile,
            "facts_by_category": by_category,
            "total_facts": len(facts),
            "categories": list(FACT_CATEGORIES),
        }
    except Exception:
        return {"user_id": user_id, "identity": {}, "facts_by_category": {}, "total_facts": 0}
