# Search tools — recherche web exposée au LLM.
#
# Extrait de app/agent/tools/__init__.py (refactor : les tools vivent
# dans app/tools/search/). Règle service-vs-tool (§7 mission) : le LLM
# décide dynamiquement d'appeler recherche_web → TOOL. Le moteur de
# recherche lui-même (web_search, ranking) reste un SERVICE
# (app/services/context/web_search.py).
from langchain_core.tools import tool

from app.logging.events import log_event


@tool
def recherche_web(
    query: str,
    max_results: int = 3,
) -> str:
    """Effectue une recherche web structurée (V6.5) et renvoie
    les résultats pertinents : titre, URL, extrait et score de
    pertinence pour chacun — jamais une chaîne concaténée brute.
    Indique clairement si la recherche est indisponible ou
    sans résultat pertinent."""

    log_event(
        "TOOL_CALL",
        message=f"recherche_web query={query}",
        tool_name="recherche_web",
    )

    from app.services.context.web_search import web_search

    response = web_search(
        user_query=query,
        subject=None,
        topic=None,
        language="fr",
        top_k=max_results,
    )

    log_event(
        "TOOL_RESULT",
        message=(
            f"recherche_web status={response.status} "
            f"results={len(response.results)}"
        ),
        tool_name="recherche_web",
    )

    if response.status == "unavailable":
        return (
            "Recherche web indisponible (service ou clé absente). "
            "Réponds avec tes connaissances générales et signale-le."
        )
    if response.status == "error":
        return (
            "Erreur de recherche web. Réponds avec tes "
            "connaissances générales et signale-le."
        )
    if not response.results:
        return (
            "Recherche web : aucun résultat pertinent trouvé. "
            "Réponds avec tes connaissances générales et signale-le."
        )

    lines = []
    for i, r in enumerate(response.results, 1):
        lines.append(
            f"[{i}] {r.title}\n    URL : {r.url}\n"
            f"    Pertinence : {r.relevance:.2f}\n"
            f"    {r.snippet or r.content[:200]}"
        )
    return "\n\n".join(lines)


search_tools = [
    recherche_web,
]

__all__ = ["recherche_web", "search_tools"]
