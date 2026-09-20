# Research Subgraph (V1) — Deep Research structurée.
#
# Requête → plan borné → recherche web multi-sources (web_search) →
# extraction de claims (web_scraper en secours) → vérification /
# comparaison de sources → synthèse sourcée → ResearchResult (§8).
#
# Exports publics (aucun second contrat créé : ResearchResult provient
# du registre existant app.graph.subgraphs.contracts).
from app.graph.subgraphs.contracts import ResearchResult
from app.graph.subgraphs.research.nodes import (
    build_initial_state,
    compile_research_subgraph,
    invoke_research_workflow,
    run_research_workflow,
)
from app.graph.subgraphs.research.state import ResearchState

__all__ = [
    "ResearchState",
    "ResearchResult",
    "compile_research_subgraph",
    "run_research_workflow",
    "invoke_research_workflow",
    "build_initial_state",
]