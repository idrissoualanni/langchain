# Node trim_context — trimming et summarization du contexte.
#
# Ce node est exécuté AVANT retrieve_context. Il nettoie l'historique
# de messages si celui-ci devient trop volumineux.
#
# LOGIQUE :
# - messages <= 30 : rien à faire (passe au node suivant)
# - messages > 30 : garde les 4 premiers + résumé du milieu + 4 derniers
#
# Le résumé du milieu est une extraction simple : on garde les premiers
# mots de chaque message du milieu (pas de LLM pour le moment).
from typing import Annotated

from langgraph.config import RunnableConfig

from app.logging.events import log_event

# Seuil de trimming (en nombre de messages)
TRIM_THRESHOLD = 30
# Nombre de messages à garder au début et à la fin
TRIM_KEEP_EDGE = 4
# Résumé du milieu : on garde les N premiers mots de chaque message
MIDDLE_SUMMARY_WORDS = 10


def trim_context_node(
    state: dict,
    config: RunnableConfig,
) -> dict:
    """Nettoie l'historique de messages si trop volumineux.

    Ce node est synchrone (opération déterministe, pas de LLM).

    Returns:
        dict: {"messages_to_remove": [ToolMessage, ...]} ou {}
    """
    messages = state.get("messages", [])
    user_id = (config.get("configurable") or {}).get("user_id", "")
    thread_id = (config.get("configurable") or {}).get("thread_id", "")

    if len(messages) <= TRIM_THRESHOLD:
        return {}

    # Calcul du slice du milieu à résumer
    middle_start = TRIM_KEEP_EDGE
    middle_end = len(messages) - TRIM_KEEP_EDGE
    middle_messages = messages[middle_start:middle_end]

    # Construction du résumé du milieu
    middle_summary = _summarize_middle(middle_messages)

    log_event(
        "TRIM_CONTEXT",
        message=(
            f"Trimming {len(messages)} messages | "
            f"keeping {TRIM_KEEP_EDGE} start + {TRIM_KEEP_EDGE} end + "
            f"summary of {len(middle_messages)} middle messages"
        ),
        user_id=user_id,
        thread_id=thread_id,
        extra={
            "total_messages": len(messages),
            "middle_count": len(middle_messages),
            "summary_preview": middle_summary[:100],
        },
    )

    # On ne supprime pas vraiment les messages ici — on retourne
    # un marqueur. C'est le prompt builder qui interprête et génère
    # le vrai résumé injecté dans le system prompt.
    return {
        "_trim_needed": True,
        "_middle_summary": middle_summary,
        "_middle_count": len(middle_messages),
        "_messages_trimmed": len(middle_messages),
    }


def _summarize_middle(messages: list) -> str:
    """Résume les messages du milieu par extraction simple.

    Pour chaque message, on garde les N premiers mots significatifs.
    """
    if not messages:
        return ""

    parts = []
    for msg in messages:
        content = getattr(msg, "content", "") or ""
        if not isinstance(content, str):
            content = str(content)

        # Extraction des premiers mots
        words = content.split()
        significant_words = [
            w for w in words
            if len(w) > 3  #过滤短词
        ]
        excerpt = " ".join(significant_words[:MIDDLE_SUMMARY_WORDS])

        if excerpt:
            msg_type = type(msg).__name__
            parts.append(f"[{msg_type}] {excerpt}")

    return " | ".join(parts)


__all__ = ["trim_context_node", "TRIM_THRESHOLD", "TRIM_KEEP_EDGE"]