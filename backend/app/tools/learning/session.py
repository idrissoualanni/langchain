# Tool learning — résumé de session.
#
# Ce tool permet de sauvegarder un résumé structuré de fin de session.
# Il est appelé soit par le LLM (en fin de session), soit par le
# SessionConsolidator (consolidation automatique).
#
# Le résumé est stocké sous namespace ("users", "learning", user_id),
# clé "session_summaries" (liste des derniers résumés).
from langchain_core.tools import tool

from app.services.learning.learning_profile import append_session_summary


@tool
def save_session_summary(
    summary: str,
    topics_covered: list[str],
    misconceptions: list[str] | None = None,
    next_steps: list[str] | None = None,
    sentiment: str | None = None,
) -> dict:
    """Enregistre un résumé structuré de la session en mémoire longue durée.

    À appeler en fin de session pour maintenir la continuité pédagogique.
    Peut aussi être appelé automatiquement par le SessionConsolidator.

    Args:
        summary: résumé textuel de la session (ce qui a été vu,
            ce qui s'est passé).
        topics_covered: liste des topics évalués pendant la session
            (ex: ["python/functions", "python/loops"]).
        misconceptions: misconceptions identifiées pendant la session.
        next_steps: suggestions de révision ou topics suivants.
        sentiment: sentiment global de la session
            (positive / neutral / negative).

    Returns:
        dict: {"saved": True, "session_id": "...", "count": N}
            où count est le nombre total de résumés stockés.
    """
    from langgraph.config import get_config

    config = get_config() or {}
    user_id = (config.get("configurable") or {}).get("user_id", "")
    thread_id = (config.get("configurable") or {}).get("thread_id", "")
    if not user_id:
        return {"error": "user_id manquant dans la config"}

    result = append_session_summary(
        user_id=user_id,
        summary=summary,
        topics_covered=topics_covered,
        misconceptions=misconceptions or [],
        next_steps=next_steps or [],
        sentiment=sentiment,
        thread_id=thread_id,
    )
    return result


__all__ = ["save_session_summary"]