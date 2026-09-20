# Evaluation → Observations (Phase 2) — pont §18.
#
# Après le scoring (EvaluationResult), une évaluation significative
# devient une LearningObservation pour le profil (jamais les messages
# ordinaires : §11). Le pont centralise la traduction PRÉCISÉMENT
# attendue par le profil (type, score, strengths, weak_points) et
# délègue au Profile Updater existant (app.learning.learning_profile),
# SANS remixer scoring et mise à jour du profil (§18).
from __future__ import annotations

from typing import Literal

from app.evaluation.schemas import EvaluationResult
from app.logging.events import log_event


def result_to_observation(
    result: EvaluationResult,
    *,
    subject: str,
    topic: str,
    observation_type: Literal["exercise", "quiz", "assessment"] = "exercise",
    confidence: float = 0.8,
) -> dict:
    """EvaluationResult §20 → champs LearningObservation §12.

    Retourne un dict prêt pour LearningObservation (module non
    importé ici pour éviter les cycles profonds / parsing Registry).
    strengths/weak_points : truncation 3 (compat profil V6).
    """
    return {
        "subject": subject,
        "topic": topic,
        "type": observation_type,
        "score": result.score,
        "strengths": (result.strengths or [])[:3],
        "weak_points": (result.weaknesses or [])[:3],
        "confidence": confidence,
    }


def emit_observation(
    *,
    user_id: str,
    thread_id: str,
    result: EvaluationResult,
    subject: str,
    topic: str,
    observation_type: Literal["exercise", "quiz", "assessment"] = "exercise",
    section_source: str = "",
) -> bool:
    """Émet l'observation du résultat au profil (non bloquant).

    Reprend le pipeline V5.2 existant (resolve_registry_topic →
    update_profile_from_observation) pour garantir l'identique :
    topic de section résolu vers le Registry, sinon rejet (§18 : on
    n'écrit jamais un topic inventé). Un échec d'écriture ne bloque
    jamais l'évaluation d'origine.
    """
    if not user_id:
        return False
    try:
        from app.learning.learning_profile import (
            resolve_registry_topic,
            update_profile_from_observation,
        )
        from app.learning.schemas import LearningObservation

        registry_topic = resolve_registry_topic(
            subject, topic, source=section_source
        )
        if not registry_topic:
            return False

        update_profile_from_observation(
            user_id,
            LearningObservation(
                **result_to_observation(
                    result,
                    subject=subject,
                    topic=registry_topic,
                    observation_type=observation_type,
                )
            ),
            thread_id=thread_id or "",
        )
        return True
    except Exception as exc:
        log_event(
            "LEARNING_PROFILE_UPDATE",
            level="WARNING",
            message=(
                f"Auto-observation via Evaluation Engine échouée "
                f"(non bloquant) : {exc}"
            ),
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "operation": "learning_observation_engine",
                "subject": subject,
                "topic": topic,
            },
        )
        return False


__all__ = [
    "result_to_observation",
    "emit_observation",
]