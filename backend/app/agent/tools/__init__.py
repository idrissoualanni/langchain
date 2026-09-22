# SHIM de compatibilité (refactor — phase migration).
#
# Les tools ont déménagé vers app/tools/ (agrégat all_tools).
# SUPPRESSION prévue phase cleanup (§30 mission) après vérification.
from app.tools import (
    all_tools,
    code_tools,
    document_tools,
    learning_tools,
    memory_tools,
    pedagogical_tools,
    search_tools,
)
from app.tools.memory import (
    delete_user_memory,
    get_user_memory,
    get_user_profile,
    save_user_memory,
    search_user_memory,
    update_user_memory,
    update_user_profile,
)
from app.tools.search import recherche_web

tools = search_tools

__all__ = [
    "tools",
    "search_tools",
    "recherche_web",
    "memory_tools",
    "pedagogical_tools",
    "learning_tools",
    "code_tools",
    "document_tools",
    "all_tools",
    "get_user_profile",
    "update_user_profile",
    "get_user_memory",
    "save_user_memory",
    "update_user_memory",
    "delete_user_memory",
    "search_user_memory",
]
