# Node retrieve_context — pré-chargement du contexte apprenant.
#
# Ce node est exécuté AVANT chaque génération LLM. Il charge
# automatiquement dans le state :
#   - Profil utilisateur (name, description)
#   - Profil d'apprentissage (mastery par topic)
#   - Concepts faibles (à réviser)
#   - Concepts forts (maîtrisés)
#   - Résumés des sessions passées
#   - Objectifs actifs
#
# Ces données sont injectées dans le system prompt via le champ
# learner_context du state. Ce champ est TRANSIENT (jamais persisté
# en checkpointer).
#
# RÈGLE : learner_context est un champ NON persisté du state.
# Il est calculé à chaque tour et nettoyé après usage.
import asyncio
from typing import Annotated

from langchain_core.messages import HumanMessage
from langgraph.config import RunnableConfig

from app.logging.events import log_event


async def retrieve_context_node(
    state: dict,
    config: RunnableConfig,
) -> dict:
    """Pré-charge le contexte apprenant avant génération LLM.

    Ce node est async pour ne pas bloquer sur les I/O store.
    Il collecte toutes les données pertinentes et les formate
    dans un bloc "Contexte Apprenant" injecté dans le system prompt.
    """
    user_id = (config.get("configurable") or {}).get("user_id", "")
    thread_id = (config.get("configurable") or {}).get("thread_id", "")

    if not user_id:
        log_event(
            "RETRIEVE_CONTEXT_SKIP",
            level="WARNING",
            message="user_id manquant — skip retrieve_context",
            thread_id=thread_id,
        )
        return {"learner_context": {}}

    log_event(
        "RETRIEVE_CONTEXT_START",
        message=f"Retrieving learner context | user={user_id}",
        user_id=user_id,
        thread_id=thread_id,
    )

    # Collecte parallèle de toutes les données
    (
        profile_data,
        learning_profile_data,
        weak_concepts_data,
        strong_concepts_data,
        past_sessions_data,
        active_goals_data,
    ) = await asyncio.gather(
        _get_user_profile_safe(user_id),
        _get_learning_profile_safe(user_id),
        _get_weak_concepts_safe(user_id),
        _get_strong_concepts_safe(user_id),
        _get_past_sessions_safe(user_id),
        _get_active_goals_safe(user_id),
    )

    # Formatage du contexte apprenant
    learner_context = {
        "profile": profile_data,
        "learning_profile": learning_profile_data,
        "weak_concepts": weak_concepts_data,
        "strong_concepts": strong_concepts_data,
        "past_sessions": past_sessions_data,
        "active_goals": active_goals_data,
    }

    # Construction du bloc system prompt
    context_block = _format_learner_context_block(learner_context)

    log_event(
        "RETRIEVE_CONTEXT_DONE",
        message=(
            f"Learner context retrieved | "
            f"subjects={len(learning_profile_data.get('subjects', {}))} | "
            f"weak={len(weak_concepts_data)} | "
            f"strong={len(strong_concepts_data)} | "
            f"sessions={len(past_sessions_data)}"
        ),
        user_id=user_id,
        thread_id=thread_id,
    )

    return {
        "learner_context": learner_context,
        "_context_block": context_block,  # temporaire, utilisé par prompt builder
    }


# --- Helpers async-safe ---


async def _get_user_profile_safe(user_id: str) -> dict:
    """Lecture du profil utilisateur (async, fail-safe)."""
    try:
        from app.services.memory.memory import read_profile

        profile = await asyncio.to_thread(read_profile, user_id)
        return {
            "name": profile.get("name"),
            "description": profile.get("description"),
        }
    except Exception as exc:
        log_event(
            "RETRIEVE_CONTEXT_ERROR",
            level="ERROR",
            message=f"Profile read failed: {exc}",
            user_id=user_id,
        )
        return {"name": None, "description": None}


async def _get_learning_profile_safe(user_id: str) -> dict:
    """Lecture du profil learning (async, fail-safe)."""
    try:
        from app.services.learning.learning_profile import read_learning_profile

        profile = await asyncio.to_thread(read_learning_profile, user_id)
        if profile is None:
            return {"subjects": {}, "goals": []}
        return profile.model_dump()
    except Exception as exc:
        log_event(
            "RETRIEVE_CONTEXT_ERROR",
            level="ERROR",
            message=f"Learning profile read failed: {exc}",
            user_id=user_id,
        )
        return {"subjects": {}, "goals": []}


async def _get_weak_concepts_safe(user_id: str) -> list:
    """Lecture des concepts faibles (async, fail-safe)."""
    try:
        from app.services.learning.learning_profile import get_weak_concepts

        return await asyncio.to_thread(get_weak_concepts, user_id, None, 0.5, 10)
    except Exception as exc:
        log_event(
            "RETRIEVE_CONTEXT_ERROR",
            level="ERROR",
            message=f"Weak concepts read failed: {exc}",
            user_id=user_id,
        )
        return []


async def _get_strong_concepts_safe(user_id: str) -> list:
    """Lecture des concepts forts (async, fail-safe)."""
    try:
        from app.services.learning.learning_profile import get_strong_concepts

        return await asyncio.to_thread(
            get_strong_concepts, user_id, None, 0.8, 10
        )
    except Exception as exc:
        log_event(
            "RETRIEVE_CONTEXT_ERROR",
            level="ERROR",
            message=f"Strong concepts read failed: {exc}",
            user_id=user_id,
        )
        return []


async def _get_past_sessions_safe(user_id: str) -> list:
    """Lecture des sessions passées (async, fail-safe)."""
    try:
        from app.services.learning.learning_profile import get_past_session_summaries

        return await asyncio.to_thread(get_past_session_summaries, user_id, 3)
    except Exception as exc:
        log_event(
            "RETRIEVE_CONTEXT_ERROR",
            level="ERROR",
            message=f"Past sessions read failed: {exc}",
            user_id=user_id,
        )
        return []


async def _get_active_goals_safe(user_id: str) -> list:
    """Lecture des objectifs actifs (async, fail-safe)."""
    try:
        from app.services.learning.learning_profile import get_active_goals

        return await asyncio.to_thread(get_active_goals, user_id)
    except Exception as exc:
        log_event(
            "RETRIEVE_CONTEXT_ERROR",
            level="ERROR",
            message=f"Active goals read failed: {exc}",
            user_id=user_id,
        )
        return []


def _format_learner_context_block(context: dict) -> str:
    """Formate le bloc Contexte Apprenant pour injection dans le system prompt."""
    lines = ["\n\n=== CONTEXTE APPRENANT (pré-chargé automatiquement) ===\n"]

    # Profil
    profile = context.get("profile", {})
    if profile.get("name"):
        lines.append(f"Nom : {profile['name']}")
    if profile.get("description"):
        lines.append(f"Description : {profile['description']}")

    # Profil learning
    lp = context.get("learning_profile", {})
    subjects = lp.get("subjects", {})
    if subjects:
        lines.append("\n--- Niveau par matière ---")
        for subject_id, subject_data in subjects.items():
            mastery = subject_data.get("mastery")
            mastery_str = f"{mastery:.0%}" if mastery is not None else "N/A"
            lines.append(
                f"  {subject_id}: mastery={mastery_str} "
                f"({len(subject_data.get('topics', {}))} topics)"
            )
            # Topis forts/faibles du subject
            for topic_id, topic_data in subject_data.get("topics", {}).items():
                t_mastery = topic_data.get("mastery")
                if t_mastery is not None:
                    if t_mastery < 0.5:
                        lines.append(
                            f"    - {topic_id}: mastery={t_mastery:.0%} "
                            f"(À REVOIR)"
                        )

    # Concepts faibles
    weak = context.get("weak_concepts", [])
    if weak:
        lines.append("\n--- Concepts à réviser ---")
        for c in weak[:5]:
            lines.append(
                f"  - {c.get('subject')}/{c.get('topic')}: "
                f"mastery={c.get('mastery', 0):.0%} "
                f"(confiance {c.get('confidence', 0):.0%})"
            )
            if c.get("weak_points"):
                lines.append(f"    Points à revoir : {', '.join(c['weak_points'][:3])}")

    # Concepts forts
    strong = context.get("strong_concepts", [])
    if strong:
        lines.append("\n--- Concepts maîtrisés ---")
        for c in strong[:5]:
            lines.append(
                f"  - {c.get('subject')}/{c.get('topic')}: "
                f"mastery={c.get('mastery', 0):.0%}"
            )

    # Sessions passées
    sessions = context.get("past_sessions", [])
    if sessions:
        lines.append("\n--- Sessions passées ---")
        for s in sessions:
            lines.append(
                f"  - [{s.get('timestamp', '')}] "
                f"Topics: {', '.join(s.get('topics_covered', [])[:3])}"
            )
            if s.get("summary"):
                lines.append(f"    Résumé: {s['summary'][:100]}...")

    # Objectifs actifs
    goals = context.get("active_goals", [])
    if goals:
        lines.append("\n--- Objectifs en cours ---")
        for g in goals:
            lines.append(
                f"  - {g.get('subject')}/{g.get('topic') or 'général'}: "
                f"{g.get('description', '')}"
            )

    lines.append("\n=== FIN CONTEXTE APPRENANT ===\n")
    return "\n".join(lines)


__all__ = ["retrieve_context_node"]