# Tools du LLM — agrégat (source unique, cf. subjects/tool_registry).
#
# Refactor (§7-§8 mission) : les tools vivent par famille dans
# app/tools/{pedagogical,memory,learning,coding,search,documents}/.
# all_tools = TOUT ce que le modèle peut appeler dynamiquement.
# Les services (moteurs, ranking, assembly) ne sont JAMAIS ici.
from app.tools.coding import code_tools
from app.tools.documents import document_tools
from app.tools.learning import learning_tools
from app.tools.memory import memory_tools
from app.tools.pedagogical import pedagogical_tools
from app.tools.search import search_tools

all_tools = (
    search_tools
    + memory_tools
    + pedagogical_tools
    + learning_tools
    + code_tools
    + document_tools
)

__all__ = [
    "search_tools",
    "memory_tools",
    "pedagogical_tools",
    "learning_tools",
    "code_tools",
    "document_tools",
    "all_tools",
]
