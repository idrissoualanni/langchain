# Learning Engine V7 — couche de DÉCISION pédagogique (§1-§26).
#
# « Quelle est la meilleure prochaine action pédagogique pour cet
# étudiant, dans ce contexte précis ? » (§1)
#
# POSITION (§3) : Router → Retrieval → Fallback → Context Builder
#                 → LEARNING ENGINE → Dynamic Prompt / LLM.
# Le moteur consomme le BuiltContext EXISTANT (§3/§26 — V6.8.1 a
# rendu ce contrat canonique) et produit UNE LearningDecision.
#
# INTERDITS RESPECTÉS :
#   §2  : PAS un deuxième agent/graphe/LLM — couche métier pure
#   §4.1: ne MODIFIE jamais le Learning Profile (lecture seule ;
#          toute écriture passe par les tools pédagogiques)
#   §17 : ne recrée PAS search_knowledge/web_search — lit
#          context.knowledge / context.web / context.fallback
#   §18 : ne recrée PAS le router — lit context.routing
#   §21 : DÉTERMINISTE — mêmes entrées → même décision (§44)
#   §24/§25 : n'exécute PAS les tools — recommended_tool seulement
from __future__ import annotations

from app.schemas.context import BuiltContext
from app.services.learning.decision import (
    ACTIVITY_TRANSITIONS,
    LearningDecision,
)
from app.services.learning.learning_profile import list_observations
from app.services.learning.rules import (
    CONFIDENCE_LOW,
    MIN_ATTEMPTS_TO_ADVANCE,
    TRAJECTORY_WINDOW,
    is_stale,
    knowledge_available,
    mastery_zone,
    read_trajectory,
    score_priority,
)
from app.logging.events import log_event

# Statuts d'activité qui bloquent toute nouvelle stratégie (§33).
_BLOCKING_STATUSES = {
    "waiting_for_answer",
    "waiting_for_retry",
    "evaluating",
    "giving_hint",
    "checking_understanding",
}


def decide(
    context: BuiltContext,
    user_id: str = "",
    thread_id: str = "",
) -> LearningDecision:
    """Décide la meilleure prochaine action pédagogique.

    Déterministe (§21/§44) : fonction PURE de BuiltContext (+ les
    observations persistées du user pour la trajectoire §11, lues
    en lecture seule). Jamais d'écriture, jamais de recherche,
    jamais de routing — le contexte est déjà construit.

    Hiérarchie de décision (§8, résolution des conflits §43) :
      1. Activité courante (PRIME — §33)
      2. Routing ambiguous/clarification (§18)
      3. Sécurité knowledge (§16 — pas d'exercice sans cours)
      4. Weak points / régression (§11/§14)
      5. Zones de maîtrise + confiance (§12/§13)
      6. Goals (§15 — orientent, n'imposent pas)
      7. Défaut answer (le LLM tuteur répond naturellement)
    """
    log_event(
        "LEARNING_ENGINE_START",
        message=(
            f"Learning engine start | user={user_id} | "
            f"subject={context.routing.subject}"
        ),
        user_id=user_id,
        thread_id=thread_id or None,
        extra={
            "operation": "learning_engine",
            "subject": context.routing.subject or "",
            "topic": context.routing.topic or "",
        },
    )
    try:
        decision = _decide_impl(context, user_id)
    except Exception as exc:
        # §19/§4 : jamais faire échouer le run — décision de repli
        # honnête + événement dédié (§46).
        log_event(
            "LEARNING_ENGINE_ERROR",
            level="ERROR",
            message=f"Learning engine error: {exc}",
            user_id=user_id,
            thread_id=thread_id or None,
            extra={
                "operation": "learning_engine",
                "error": str(exc)[:300],
            },
        )
        decision = LearningDecision(
            action="answer",
            subject=context.routing.subject,
            topic=context.routing.topic,
            reason=(
                "Décision pédagogique indisponible — réponse "
                "directe du tuteur."
            ),
            confidence=0.1,
            priority=0,
        )
    log_event(
        "LEARNING_DECISION",
        message=(
            f"Learning decision | user={user_id} | "
            f"action={decision.action} | "
            f"{decision.subject or '-'}/{decision.topic or '-'} | "
            f"priority={decision.priority}"
        ),
        user_id=user_id,
        thread_id=thread_id or None,
        extra={
            "operation": "learning_engine",
            "subject": decision.subject,
            "topic": decision.topic,
            "action": decision.action,
            "reason": decision.reason[:200],
            "confidence": decision.confidence,
            "priority": decision.priority,
            "recommended_tool": decision.recommended_tool or "",
        },
    )
    log_event(
        "LEARNING_ENGINE_END",
        message=(
            f"Learning engine end | action={decision.action}"
        ),
        user_id=user_id,
        thread_id=thread_id or None,
        extra={
            "operation": "learning_engine",
            "action": decision.action,
        },
    )
    return decision


def _decide_impl(
    context: BuiltContext, user_id: str
) -> LearningDecision:
    """Implémentation déterministe — hiérarchie §8/§43."""
    routing = context.routing
    subject = routing.subject
    topic = routing.topic
    learning = context.learning
    activity = context.activity
    knowledge_ok = knowledge_available(
        context.knowledge.status
    )

    # --- 1. ACTIVITÉ COURANTE PRIME (§8/§33) -------------------
    if (
        activity is not None
        and activity.status in _BLOCKING_STATUSES
    ):
        allowed = ACTIVITY_TRANSITIONS.get(
            activity.status, ()
        )
        # L'étudiant vient de répondre ? → évaluer. Sinon
        # poursuivre/aider l'activité en cours.
        action = (
            "evaluate"
            if activity.status
            in ("waiting_for_answer", "waiting_for_retry")
            and "evaluate" in allowed
            else "continue_activity"
        )
        return LearningDecision(
            action=action,
            subject=activity.subject or subject,
            topic=activity.topic or topic,
            reason=(
                f"Une activité {activity.activity_type} est en "
                f"cours ({activity.status}) — terminer la boucle "
                "pédagogique courante avant toute nouvelle "
                "stratégie."
            ),
            confidence=0.9,
            priority=score_priority(has_current_activity=True),
            activity_id=activity.activity_id or None,
            recommended_tool=(
                "evaluate_answer"
                if action == "evaluate"
                else None
            ),
            metadata={
                "activity_status": activity.status,
                "hint_level": activity.hint_level,
                "attempts": activity.attempts,
            },
        )

    # --- 2. CLARIFICATION (§18 : ambiguous → clarify) ----------
    if routing.status == "ambiguous":
        return LearningDecision(
            action="clarify",
            subject=subject,
            topic=topic,
            reason=(
                "La demande est ambiguë entre plusieurs matières — "
                "demander une précision avant de choisir une "
                "stratégie."
            ),
            confidence=0.8,
            priority=score_priority(),
            metadata={"candidates": list(routing.candidates)},
        )

    # --- 3. SÉCURITÉ KNOWLEDGE (§16) ---------------------------
    # Matière sans cours exploitable : pas d'exercice inventé
    # sur une connaissance inexistante — le fallback V6.6 a déjà
    # tranché (answer / général / web).
    if not knowledge_ok and routing.subject is not None:
        fb = context.fallback
        return LearningDecision(
            action="answer",
            subject=subject,
            topic=topic,
            reason=(
                "Le cours ne fournit pas de contenu exploitable "
                "pour ce sujet — réponse directe du tuteur, sans "
                "activité fabriquée."
            ),
            confidence=0.6,
            priority=score_priority(),
            metadata={
                "knowledge_status": context.knowledge.status,
                "fallback_action": fb.action,
            },
        )

    # --- 4. PAS DE PROFIL / PAS DE PROGRESSION (§19/§20) -------
    if (
        learning is None
        or learning.status != "active"
    ):
        # not_started ≠ error : premier contact — expliquer puis
        # proposer une pratique simple (sans inventer de
        # progression §20).
        return LearningDecision(
            action="explain",
            subject=subject,
            topic=topic,
            reason=(
                "Premier contact sur ce sujet — expliquer le "
                "concept, sans présupposer de progression."
            ),
            confidence=0.7,
            priority=score_priority(),
            recommended_tool=(
                "create_exercise"
                if routing.status == "supported"
                else None
            ),
            metadata={"learning_status": "not_started"},
        )

    # --- 5. TRAJECTOIRE + WEAK POINTS (§11/§14) ---------------
    scores = _recent_scores(user_id, subject, topic)
    trajectory = read_trajectory(scores)
    stale = is_stale(learning.last_assessed_at)
    has_weak = bool(learning.weak_points)
    zone = mastery_zone(learning.mastery)
    low_conf = (
        learning.confidence is not None
        and learning.confidence < CONFIDENCE_LOW
    )
    priority = score_priority(
        has_active_goal=_goal_active(learning),
        has_weak_points=has_weak,
        mastery_zone_=zone,
        trajectory=trajectory,
        confidence=learning.confidence,
        stale=stale,
    )

    # Régression (§11) : même mastery élevée → réviser d'abord.
    if trajectory == "regression" and zone in (
        "developing", "proficient", "strong"
    ):
        return LearningDecision(
            action="review",
            subject=subject,
            topic=topic,
            reason=(
                "Les derniers résultats marquent une régression "
                "— consolider ce topic avant d'avancer."
            ),
            confidence=0.75,
            priority=priority,
            recommended_tool="create_exercise",
            metadata={
                "trajectory": trajectory,
                "mastery": learning.mastery,
                "zone": zone,
            },
        )

    # Confiance trop basse (§13) : quelle que soit la zone, on
    # CONFIRME avant d'avancer — mastery 0.78 + confidence 0.24
    # → evaluate, PAS advance.
    if low_conf and zone in ("proficient", "strong"):
        return LearningDecision(
            action="evaluate",
            subject=subject,
            topic=topic,
            reason=(
                "Maîtrise estimée élevée mais peu confirmée "
                f"({zone}) — une évaluation pour la valider "
                "avant d'avancer."
            ),
            confidence=0.7,
            priority=priority,
            recommended_tool="assess_understanding",
            metadata={"zone": zone, "low_confidence": True},
        )

    # Weak point récent (§14) : cible prioritaire sur le topic,
    # toutes zones — besoin réel > avance vers du nouveau.
    if has_weak:
        return LearningDecision(
            action="practice",
            subject=subject,
            topic=topic,
            reason=(
                "Des points faibles récents sont identifiés "
                f"({'; '.join(learning.weak_points[:2])}) — "
                "pratique ciblée pour les consolider."
            ),
            confidence=0.8,
            priority=priority,
            recommended_tool="create_exercise",
            metadata={
                "weak_points": learning.weak_points[:3],
                "zone": zone,
            },
        )

    # --- 6. ZONES DE MAÎTRISE (§12/§13) -----------------------
    if zone == "weak":
        # §13 : mastery + confidence basse → évaluer d'abord pour
        # vérifier l'estimation ; sinon revoir les fondamentaux.
        if low_conf and (learning.attempts or 0) < 1:
            return LearningDecision(
                action="evaluate",
                subject=subject,
                topic=topic,
                reason=(
                    "Niveau estimé peu fiable — une évaluation "
                    "rapide pour situer l'étudiant avant de "
                    "choisir la suite."
                ),
                confidence=0.65,
                priority=priority,
                recommended_tool="assess_understanding",
                metadata={"zone": zone},
            )
        return LearningDecision(
            action="review",
            subject=subject,
            topic=topic,
            reason=(
                "Maîtrise encore fragile de ce topic — reprendre "
                "les fondamentaux avec une révision guidée."
            ),
            confidence=0.75,
            priority=priority,
            recommended_tool="create_exercise",
            metadata={"zone": zone, "stale": stale},
        )

    if zone == "developing":
        # Zone de travail : alterner explication et pratique.
        if (learning.attempts or 0) < MIN_ATTEMPTS_TO_ADVANCE:
            return LearningDecision(
                action="practice",
                subject=subject,
                topic=topic,
                reason=(
                    "Maîtrise en construction — une pratique "
                    "supplémentaire pour consolider."
                ),
                confidence=0.78,
                priority=priority,
                recommended_tool="create_exercise",
                metadata={"zone": zone},
            )
        return LearningDecision(
            action="practice",
            subject=subject,
            topic=topic,
            reason=(
                "Maîtrise intermédiaire confirmée — poursuivre "
                "la pratique pour atteindre l'autonomie."
            ),
            confidence=0.8,
            priority=priority,
            recommended_tool="create_quiz",
            metadata={"zone": zone},
        )

    if zone == "proficient":
        # (§13 low_conf traité globalement avant les zones.)
        if stale:
            return LearningDecision(
                action="review",
                subject=subject,
                topic=topic,
                reason=(
                    "Topic maîtrisé mais non revisité depuis "
                    "longtemps — une révision courte pour l'entretenir."
                ),
                confidence=0.7,
                priority=priority,
                recommended_tool="create_quiz",
                metadata={"zone": zone, "stale": True},
            )
        return LearningDecision(
            action="deepen",
            subject=subject,
            topic=topic,
            reason=(
                "Topic bien maîtrisé — proposer un angle "
                "d'approfondissement."
            ),
            confidence=0.8,
            priority=priority,
            recommended_tool=None,
            metadata={"zone": zone},
        )

    # zone strong
    if (learning.attempts or 0) >= MIN_ATTEMPTS_TO_ADVANCE:
        # §15 : un goal actif sur CE sujet oriente l'avancée.
        goal = learning.goal
        if (
            goal is not None
            and goal.status == "active"
            and goal.topic
            and goal.topic != topic
        ):
            return LearningDecision(
                action="advance_topic",
                subject=subject,
                topic=goal.topic,
                reason=(
                    f"Topic maîtrisé — l'objectif actif "
                    f"(« {goal.description[:60]} ») pointe vers "
                    f"« {goal.topic} »."
                ),
                confidence=0.75,
                priority=priority,
                metadata={"goal_id": goal.id},
            )
        return LearningDecision(
            action="advance_topic",
            subject=subject,
            topic=topic,
            reason=(
                "Maîtrise consolidée de ce topic — proposer le "
                "topic suivant pertinent."
            ),
            confidence=0.8,
            priority=priority,
            metadata={"zone": "strong"},
        )

    # strong mais tentatives insuffisantes → confirmer
    return LearningDecision(
        action="quiz",
        subject=subject,
        topic=topic,
        reason=(
            "Niveau élevé sur peu d'évaluations — un quiz de "
            "confirmation avant d'avancer."
        ),
        confidence=0.7,
        priority=priority,
        recommended_tool="create_quiz",
        metadata={"zone": "strong"},
    )


def _recent_scores(
    user_id: str,
    subject: str | None,
    topic: str | None,
) -> list[float | None]:
    """Derniers scores du topic (§11) — lecture SEULE, défensive."""
    if not user_id or not subject or not topic:
        return []
    try:
        obs = list_observations(user_id, subject, topic)
        return [
            o.get("score") for o in obs[-TRAJECTORY_WINDOW:]
        ]
    except Exception:
        return []


def _goal_active(learning) -> bool:
    """Goal actif sur ce sujet/topic (§15) — oriente la priorité."""
    goal = getattr(learning, "goal", None)
    return bool(
        goal is not None
        and getattr(goal, "status", None) == "active"
    )


__all__ = ["decide"]
