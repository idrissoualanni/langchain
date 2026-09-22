# Services memory — mémoire longue durée cross-thread (User Memory).
#
#   memory.py : store SQLite (profil + MemoryFacts), get_store/singleton.
# Les tools LLM (lecture/écriture mémoire) vivent dans app/tools/memory/.
from app.services.memory.memory import (
    FACT_CATEGORIES,
    delete_fact,
    get_store,
    list_facts,
    memory_overview_for_api,
    read_profile,
    read_profile_for_api,
    save_fact,
    search_facts,
    update_fact,
    write_profile,
)

__all__ = [
    "FACT_CATEGORIES",
    "delete_fact",
    "get_store",
    "list_facts",
    "memory_overview_for_api",
    "read_profile",
    "read_profile_for_api",
    "save_fact",
    "search_facts",
    "update_fact",
    "write_profile",
]
