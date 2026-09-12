# Routes Learning V6 — Learning Profile exposé au frontend.
#
# GET /api/learning/{user_id}/profile           → profil complet
# GET /api/learning/{user_id}/{subject}/topics  → sujets travaillés
# GET /api/learning/{user_id}/{subject}/{topic} → état d'un topic
# GET /api/learning/{user_id}/observations      → historique (§33)
# GET /api/learning/{user_id}/goals             → objectifs
#
# Les tools LLM (record_learning_observation) restent la voie
# d'écriture principale — ces routes sont en LECTURE pour
# l'affichage (§35/§36 : progression + raw inspector).
from fastapi import APIRouter, HTTPException, Query

from app.db.connections import init_db
from app.db.users import get_user
from app.learning.learning_profile import (
    list_observations,
    read_learning_profile,
)
from app.logging.events import log_event

router = APIRouter(prefix="/api/learning", tags=["learning"])


def _require_user(user_id: str) -> None:
    init_db()
    if get_user(user_id) is None:
        raise HTTPException(
            status_code=404, detail="Utilisateur introuvable"
        )


@router.get("/{user_id}/profile")
def api_learning_profile(user_id: str) -> dict:
    """Learning Profile complet (§36 — raw inspector).

    Retourne {"status": "not_started"} si aucun profil (§26 —
    cas normal, pas une erreur).
    """
    _require_user(user_id)
    profile = read_learning_profile(user_id)
    if profile is None:
        return {"status": "not_started", "user_id": user_id}
    data = profile.model_dump()
    data["status"] = "active"
    return data


@router.get("/{user_id}/observations")
def api_learning_observations(
    user_id: str,
    subject: str | None = Query(default=None),
    topic: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict]:
    """Historique des observations (§33), filtrable."""
    _require_user(user_id)
    obs = list_observations(user_id, subject=subject, topic=topic)
    return obs[-limit:]


@router.get("/{user_id}/topics")
def api_learning_topics(user_id: str) -> dict:
    """Tous les états de topics travaillés, groupés par matière (§35)."""
    _require_user(user_id)
    profile = read_learning_profile(user_id)
    if profile is None:
        return {"status": "not_started", "subjects": {}}

    subjects: dict[str, dict] = {}
    for sid, state in profile.subjects.items():
        subjects[sid] = {
            "mastery": state.mastery,
            "topics": {
                tid: t.model_dump()
                for tid, t in state.topics.items()
            },
        }
    return {"status": "active", "subjects": subjects}


@router.get("/{user_id}/{subject}/{topic}")
def api_learning_topic(
    user_id: str, subject: str, topic: str
) -> dict:
    """État d'apprentissage d'UN topic (§21)."""
    _require_user(user_id)
    profile = read_learning_profile(user_id)
    if profile is None:
        return {
            "status": "not_started",
            "subject": subject,
            "topic": topic,
        }
    subject_state = profile.subjects.get(subject)
    topic_state = (
        subject_state.topics.get(topic) if subject_state else None
    )
    if topic_state is None:
        return {
            "status": "not_started",
            "subject": subject,
            "topic": topic,
        }
    data = topic_state.model_dump()
    data["status"] = "active"
    data["subject"] = subject
    data["topic"] = topic
    data["subject_mastery"] = (
        subject_state.mastery if subject_state else None
    )
    log_event(
        "LEARNING_PROFILE_READ",
        message=(
            f"Topic state read via API | user={user_id} | "
            f"{subject}/{topic}"
        ),
        user_id=user_id,
        extra={
            "operation": "learning_topic_read",
            "subject": subject,
            "topic": topic,
        },
    )
    return data


@router.get("/{user_id}/goals")
def api_learning_goals(user_id: str) -> list[dict]:
    """Objectifs d'apprentissage de l'étudiant (§29)."""
    _require_user(user_id)
    profile = read_learning_profile(user_id)
    if profile is None:
        return []
    return [g.model_dump() for g in profile.goals]
