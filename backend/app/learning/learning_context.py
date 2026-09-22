# Learning Context V6 — sélection pertinente pour le Context Builder
# (§24/§25) + interface Learning Engine future (§41).
#
# PRINCIPE (§25) : pour « Je veux continuer les fonctions Python »,
# le contexte learning doit contenir Python/functions (mastery,
# weak_points, attempts) — PAS toute la biologie ni tous les goals.
#
# Règles de sélection :
#   1. topic routé + topic dans le profil   → état réel du topic
#   2. topic routé + topic inconnu du profil
#      mais connu du Registry               → état minimal §28
#      (mastery null, attempts 0) — information utile : « pas
#      encore travaillé », pas une erreur
#   3. sujet routé sans topic               → meilleur topic du
#      sujet (le moins maîtrisé) + mastery sujet
#   4. pas de sujet routé / pas de profil   → status not_started
#      (§26) — le tuteur fonctionne sans Learning Profile
from __future__ import annotations

from app.learning.learning_profile import (
    get_topic_state,
    read_learning_profile,
)
from app.schemas.learning import (
    LearningContextInfo,
    LearningGoal,
    TopicLearningState,
)
from app.logging.events import log_event


def _goal_for(
    profile_subject_goals: list[LearningGoal],
) -> LearningGoal | None:
    """Goal actif prioritaire (le plus récent créé pour le sujet)."""
    active = [
        g for g in profile_subject_goals if g.status == "active"
    ]
    return active[-1] if active else None


def get_learning_context(
    user_id: str,
    subject: str | None,
    topic: str | None,
    thread_id: str = "",
) -> LearningContextInfo:
    """Sélectionne le contexte learning PERTINENT pour un run.

    Interface stable consommée par le Context Builder V6 et par
    le futur Learning Engine V7 (§41). Ne lève JAMAIS (§26) :
    toute erreur de lecture → status "unavailable", loggé.
    """
    try:
        # --- Sujet non routé (unknown/unsupported) : pas de
        # sélection learning (§24 — rien à sélectionner) ---
        if not subject:
            return LearningContextInfo(status="not_started")

        profile = read_learning_profile(user_id)
        if profile is None:
            # §26 : nouvel étudiant — cas NORMAL, pas une erreur
            log_event(
                "LEARNING_CONTEXT_SELECTED",
                message=(
                    f"Learning context | user={user_id} | "
                    f"status=not_started (no profile)"
                ),
                user_id=user_id,
                thread_id=thread_id or None,
                extra={
                    "operation": "learning_context_selected",
                    "subject": subject,
                    "topic": topic or "",
                    "learning_status": "not_started",
                },
            )
            return LearningContextInfo(
                status="not_started",
                subject=subject,
                topic=topic,
            )

        subject_state = profile.subjects.get(subject)

        # --- Topic explicite : cas 1 (état réel) / cas 2 (§28) ---
        if topic:
            topic_state: TopicLearningState | None = (
                subject_state.topics.get(topic)
                if subject_state
                else None
            )
            if topic_state is None and subject_state:
                # Fallback canonique (mission intégration) : le
                # router peut router l'alias FR (« fonctions »)
                # alors que le profil indexe le stem EN
                # (« functions ») — même fichier knowledge ⇒
                # même progression. On cherche la clé canonique
                # SANS inventer de topic.
                from app.context.knowledge_retriever import (
                    resolve_topic_source,
                )

                canonical = resolve_topic_source(subject, topic)
                if canonical:
                    from app.subjects.registry import get_subject

                    cfg_r = get_subject(subject)
                    stem = canonical[0].rsplit("/", 1)[-1]
                    if cfg_r and stem in cfg_r.topics:
                        topic_state = subject_state.topics.get(
                            stem
                        )
                        if topic_state is not None:
                            topic = stem
            if topic_state is not None:
                info = LearningContextInfo(
                    status="active",
                    subject=subject,
                    topic=topic,
                    mastery=topic_state.mastery,
                    attempts=topic_state.attempts,
                    strengths=list(topic_state.strengths),
                    weak_points=list(topic_state.weak_points),
                    last_assessed_at=topic_state.last_assessed_at,
                    confidence=topic_state.confidence,
                    subject_mastery=(
                        subject_state.mastery
                        if subject_state
                        else None
                    ),
                    goal=_goal_for(
                        [
                            g
                            for g in profile.goals
                            if g.subject == subject
                        ]
                    ),
                )
                _log_selected(user_id, thread_id, info)
                return info

            # Topic inconnu du profil : §28 — s'il est connu du
            # Registry, on signale « pas encore travaillé » ;
            # sinon le topic est peut-être routé hors Registry
            # (unsupported) → not_started sans invention.
            from app.subjects.registry import get_subject

            cfg = get_subject(subject)
            if cfg and topic in cfg.topics:
                info = LearningContextInfo(
                    status="active",
                    subject=subject,
                    topic=topic,
                    mastery=None,
                    attempts=0,
                    subject_mastery=(
                        subject_state.mastery
                        if subject_state
                        else None
                    ),
                    goal=_goal_for(
                        [
                            g
                            for g in profile.goals
                            if g.subject == subject
                        ]
                    ),
                )
                _log_selected(user_id, thread_id, info)
                return info

            return LearningContextInfo(
                status="not_started",
                subject=subject,
                topic=topic,
            )

        # --- Pas de topic routé (cas 3) : le sujet existe-t-il
        # dans le profil ? Si oui → topic le plus faible
        # (pédagogiquement utile : « on en était là ») ---
        if subject_state and subject_state.topics:
            # Topic le moins maîtrisé parmi ceux évalués ; sinon
            # le dernier travaillé (dernier de la dict).
            assessed = [
                (tid, t)
                for tid, t in subject_state.topics.items()
                if t.mastery is not None
            ]
            if assessed:
                tid, t = min(
                    assessed, key=lambda x: x[1].mastery or 0.0
                )
            else:
                tid, t = list(subject_state.topics.items())[-1]

            info = LearningContextInfo(
                status="active",
                subject=subject,
                topic=tid,
                mastery=t.mastery,
                attempts=t.attempts,
                strengths=list(t.strengths),
                weak_points=list(t.weak_points),
                last_assessed_at=t.last_assessed_at,
                confidence=t.confidence,
                subject_mastery=subject_state.mastery,
                goal=_goal_for(
                    [
                        g
                        for g in profile.goals
                        if g.subject == subject
                    ]
                ),
            )
            _log_selected(user_id, thread_id, info)
            return info

        # Sujet connu du profil mais sans topics : signaler le
        # sujet sans inventer de topic.
        return LearningContextInfo(
            status="active" if subject_state else "not_started",
            subject=subject,
            subject_mastery=(
                subject_state.mastery if subject_state else None
            ),
            goal=_goal_for(
                [g for g in profile.goals if g.subject == subject]
            ),
        )

    except Exception as exc:
        # §26 : erreur de lecture → unavailable, jamais de crash
        log_event(
            "LEARNING_CONTEXT_SELECTED",
            level="ERROR",
            message=f"Learning context error: {exc}",
            user_id=user_id,
            thread_id=thread_id or None,
            extra={
                "operation": "learning_context_selected",
                "error": str(exc)[:300],
            },
        )
        return LearningContextInfo(status="unavailable")


def _log_selected(
    user_id: str,
    thread_id: str,
    info: LearningContextInfo,
) -> None:
    """LEARNING_CONTEXT_SELECTED (§38) — avant CONTEXT_BUILD_END."""
    log_event(
        "LEARNING_CONTEXT_SELECTED",
        message=(
            f"Learning context | user={user_id} | "
            f"{info.subject}/{info.topic} | "
            f"status={info.status} | mastery={info.mastery} | "
            f"attempts={info.attempts}"
        ),
        user_id=user_id,
        thread_id=thread_id or None,
        extra={
            "operation": "learning_context_selected",
            "subject": info.subject or "",
            "topic": info.topic or "",
            "learning_status": info.status,
            "mastery": info.mastery,
            "attempts": info.attempts,
        },
    )


def _ensure_topic_state(
    user_id: str, subject: str, topic: str
) -> TopicLearningState:
    """État topic minimal si nécessaire (§28 — helper interne).

    Utilisé uniquement quand le Context Builder veut exposer un
    topic Registry jamais travaillé : crée mastery=null,
    attempts=0 SANS observation (pas de maîtrise inventée).
    """
    existing = get_topic_state(user_id, subject, topic)
    if existing is not None:
        return existing
    return TopicLearningState()


__all__ = ["get_learning_context"]
