# SHIM de compatibilité (refactor — phase migration).
#
# Le service mémoire a déménagé vers app/services/memory/memory.py.
# SUPPRESSION prévue phase cleanup (§30 mission) après vérification.
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
