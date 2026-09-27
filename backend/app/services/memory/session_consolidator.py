# Session Consolidator — consolidation automatique de fin de session.
#
# Ce service est appelé côté API (chat.py) quand :
#   - interaction_count > 10, OU
#   - flag session_ending=True
#
# LOGIQUE :
# 1. Lit le checkpoint courant → extrait topics + activity_log
# 2. Génère un résumé structuré (summary, misconceptions, next_steps)
# 3. Appelle append_session_summary(user_id, summary)
# 4. Log SESSION_CONSOLIDATED
#
# NOTE : la consolidation est BEST-EFFORT. Si elle échoue, on log
# l'erreur mais on ne bloque pas la réponse API.
import asyncio
from typing import Optional

from app.logging.events import log_event


async def consolidate_session(
    user_id: str,
    thread_id: str,
    agent,
    config: dict,
) -> dict:
    """Consolide la session en mémoire longue durée.

    Args:
        user_id: identifiant de l'apprenant.
        thread_id: identifiant du thread.
        agent: instance de l'agent LangGraph.
        config: config LangGraph (avec configurable.thread_id, etc.).

    Returns:
        dict: {"consolidated": True, "session_id": ...} ou
              {"consolidated": False, "error": "..."}
    """
    from app.services.learning.learning_profile import append_session_summary

    log_event(
        "SESSION_CONSOLIDATION_START",
        message=f"Session consolidation started | user={user_id} | thread={thread_id}",
        user_id=user_id,
        thread_id=thread_id,
    )

    try:
        # 1. Lire le state courant depuis le checkpointer
        snapshot = agent.get_state(config)
        if not snapshot or not snapshot.values:
            return {"consolidated": False, "error": "No state found"}

        values = snapshot.values

        # 2. Extraire les topics couverts depuis l'activity_log
        activity_log = values.get("activity_log", [])
        topics_covered = _extract_topics_from_activity_log(activity_log)

        # 3. Extraire les misconceptions de l'activité en cours
        learning_activity = values.get("learning_activity", {})
        misconceptions = _extract_misconceptions(learning_activity)

        # 4. Construire le résumé textuel
        summary = _build_summary(activity_log, learning_activity)

        # 5. Inférer les next_steps depuis les weak_points
        next_steps = _infer_next_steps(learning_activity, topics_covered)

        # 6. Sentiment basé sur l'activité
        sentiment = _infer_sentiment(learning_activity)

        # 7. Sauvegarder en mémoire longue durée
        result = await asyncio.to_thread(
            append_session_summary,
            user_id=user_id,
            summary=summary,
            topics_covered=topics_covered,
            misconceptions=misconceptions,
            next_steps=next_steps,
            sentiment=sentiment,
            thread_id=thread_id,
        )

        log_event(
            "SESSION_CONSOLIDATED",
            message=(
                f"Session consolidated | user={user_id} | "
                f"topics={len(topics_covered)} | "
                f"session_count={result.get('count', 0)}"
            ),
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "topics_covered": topics_covered,
                "misconceptions": misconceptions,
                "session_count": result.get("count", 0),
            },
        )

        return {
            "consolidated": True,
            "session_id": result.get("session_id", ""),
            "topics_covered": topics_covered,
            "count": result.get("count", 0),
        }

    except Exception as exc:
        log_event(
            "SESSION_CONSOLIDATION_ERROR",
            level="ERROR",
            message=f"Session consolidation failed: {exc}",
            user_id=user_id,
            thread_id=thread_id,
        )
        return {"consolidated": False, "error": str(exc)[:200]}


def _extract_topics_from_activity_log(activity_log: list) -> list[str]:
    """Extrait les topics couverts depuis l'activity_log."""
    topics = set()
    for entry in activity_log:
        detail = entry.get("detail", "")
        # Format attendu : "exercise python/functions" ou "quiz python/loops"
        parts = detail.split()
        if len(parts) >= 2:
            # Le premier mot est le type (exercise, quiz, etc.)
            # Le reste est le topic
            topic_part = " ".join(parts[1:])
            if "/" in topic_part:
                topics.add(topic_part)
            elif topic_part in ("python", "biology", "mathematics"):
                # Matière sans topic précis
                topics.add(topic_part)
    return list(topics)


def _extract_misconceptions(learning_activity: dict) -> list[str]:
    """Extrait les misconceptions depuis l'activité en cours."""
    if not learning_activity:
        return []

    misconceptions = []

    # Des weak_points de l'évaluation
    last_eval = learning_activity.get("last_evaluation", {})
    if isinstance(last_eval, dict):
        missing = last_eval.get("missing", [])
        if isinstance(missing, list):
            misconceptions.extend([str(m) for m in missing[:5]])

    return list(set(misconceptions))  # déduplication


def _build_summary(activity_log: list, learning_activity: dict) -> str:
    """Construit un résumé textuel de la session."""
    if not activity_log:
        return "Session sans activité pédagogique."

    # Compter les types d'activités
    exercise_count = sum(
        1 for e in activity_log if "exercise" in e.get("detail", "")
    )
    quiz_count = sum(
        1 for e in activity_log if "quiz" in e.get("detail", "")
    )
    hint_count = sum(
        1 for e in activity_log if "HINT" in e.get("event", "")
    )

    summary_parts = []
    if exercise_count > 0:
        summary_parts.append(f"{exercise_count} exercice(s)")
    if quiz_count > 0:
        summary_parts.append(f"{quiz_count} question(s) de quiz")
    if hint_count > 0:
        summary_parts.append(f"{hint_count} indice(s) utilisé(s)")

    summary = ", ".join(summary_parts) if summary_parts else "Session de conversation"

    # Ajouter le sentiment global
    last_eval = learning_activity.get("last_evaluation", {})
    if isinstance(last_eval, dict):
        verdict = last_eval.get("verdict", "")
        if verdict:
            summary += f". Dernière évaluation : {verdict.lower()}."

    return summary


def _infer_next_steps(
    learning_activity: dict,
    topics_covered: list[str],
) -> list[str]:
    """Infère les next_steps suggérés."""
    suggestions = []

    # Basé sur le last_evaluation
    last_eval = learning_activity.get("last_evaluation", {})
    if isinstance(last_eval, dict):
        missing = last_eval.get("missing", [])
        if isinstance(missing, list) and missing:
            suggestions.append(f"Revoir les points manquants : {', '.join(missing[:3])}")

    # Basé sur le hint_level
    hint_level = learning_activity.get("hint_level", 0)
    if hint_level >= 2:
        suggestions.append("Reprendre le concept depuis le début avec des exemples simples")

    # Sitopics_covered et pas de suggestions, proposer une révision
    if topics_covered and not suggestions:
        suggestions.append(f"Continuer avec un autre topic de {' / '.join(topics_covered[:2])}")

    return suggestions[:3]  # max 3


def _infer_sentiment(learning_activity: dict) -> str:
    """Infère le sentiment global de la session."""
    last_eval = learning_activity.get("last_evaluation", {})
    if not isinstance(last_eval, dict):
        return "neutral"

    score = last_eval.get("score", 0.5)
    if score >= 0.75:
        return "positive"
    elif score >= 0.4:
        return "neutral"
    else:
        return "negative"


__all__ = ["consolidate_session"]