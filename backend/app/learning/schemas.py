# Learning Schemas V6 — Learning Profile structuré (§7-§12, §29).
#
# Distinction fondamentale des trois mémoires (§1/§3/§4) :
#   USER MEMORY      = qui est l'étudiant ? (namespace users/profile)
#   THREAD STATE     = que se passe-t-il maintenant ? (checkpointer)
#   LEARNING PROFILE = où en est l'étudiant ? (namespace users/learning)
#
# mastery n'est PAS une vérité absolue (§9) : c'est une ESTIMATION
# assortie d'une confidence — on distingue « estimation » de
# « fait certain ». Les observations (§12) sont séparées du profil :
# elles décrivent un événement pédagogique, le Profile Updater
# (learning_profile.py) décide comment les intégrer (§13).
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

# Sources des observations (§10) — toutes les observations ne se
# valent pas : assessment/teacher pèsent plus qu'inferred.
OBSERVATION_SOURCES = (
    "exercise",
    "quiz",
    "assessment",
    "teacher_feedback",
)


def _now() -> str:
    """Timestamp ISO 8601 UTC (convention projet)."""
    return datetime.now(timezone.utc).isoformat()


class TopicLearningState(BaseModel):
    """État d'apprentissage d'UN topic d'une matière (§7).

    mastery null = jamais évalué (§27/§28) — PAS une erreur :
    un topic commencé sans observation reste à (null, 0).
    """

    mastery: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Estimation de maîtrise [0..1] — null si "
        "jamais évalué",
    )
    attempts: int = Field(
        default=0,
        description="Nombre d'observations intégrées pour ce topic",
    )
    strengths: list[str] = Field(
        default_factory=list,
        description="Points forts observés (liés à CE topic, §30)",
    )
    weak_points: list[str] = Field(
        default_factory=list,
        description="Points faibles observés (liés à CE topic, §30)",
    )
    last_assessed_at: str | None = Field(
        default=None,
        description="Dernière observation intégrée (ISO 8601 UTC)",
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confiance de l'estimation mastery [0..1] — "
        "null si jamais évalué (§9)",
    )


class SubjectLearningState(BaseModel):
    """État d'apprentissage d'UNE matière (§7/§16)."""

    mastery: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Agrégation des topics (moyenne pondérée par "
        "attempts) — null si aucun topic évalué",
    )
    topics: dict[str, TopicLearningState] = Field(
        default_factory=dict,
        description="Topics vus, clé = topic_id du Subject Registry",
    )


class LearningGoal(BaseModel):
    """Objectif d'apprentissage déclaré (§29).

    Séparé de la maîtrise : un objectif peut être actif même
    si mastery est haute, et réciproquement.
    """

    id: str = Field(description="Identifiant unique du goal")
    subject: str = Field(description="subject_id du Registry")
    topic: str | None = Field(
        default=None,
        description="topic_id ciblé si précis (optionnel)",
    )
    description: str = Field(description="Objectif en langage clair")
    status: Literal["active", "completed", "paused"] = Field(
        default="active",
    )
    created_at: str = Field(default_factory=_now)


class LearningObservation(BaseModel):
    """Observation pédagogique SIGNIFICATIVE (§12).

    Créée par exercise evaluation / quiz / assessment / teacher
    correction. Un message ordinaire NE DOIT JAMAIS produire
    d'observation (§11). Le score est optionnel (un feedback
    qualitatif teacher n'a pas forcément de score).
    """

    subject: str = Field(description="subject_id (validé Registry)")
    topic: str = Field(description="topic_id (validé Registry)")
    type: Literal[
        "exercise",
        "quiz",
        "assessment",
        "teacher_feedback",
    ] = Field(description="Nature de l'observation (§10)")
    score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Score normalisé [0..1] si quantifiable",
    )
    strengths: list[str] = Field(default_factory=list)
    weak_points: list[str] = Field(default_factory=list)
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Fiabilité de l'observation (source-weighted, §10)",
    )
    created_at: str = Field(default_factory=_now)


class LearningProfile(BaseModel):
    """Profil d'apprentissage persistant d'un étudiant (§7).

    Stocké dans le SqliteStore sous namespace ("users", "learning",
    user_id), clé "profile" — cross-thread (§4), jamais de messages
    (§34 : les messages restent dans le Checkpointer).
    """

    user_id: str
    subjects: dict[str, SubjectLearningState] = Field(
        default_factory=dict,
        description="Clé = subject_id du Registry",
    )
    goals: list[LearningGoal] = Field(default_factory=list)
    updated_at: str = Field(default_factory=_now)


class LearningContextInfo(BaseModel):
    """Sélection Learning Profile PERTINENTE pour un run (§24/§25).

    C'est ce qui alimente BuiltContext.learning : uniquement
    le subject/topic de la question courante — JAMAIS tout le
    profil (pas de biologie pour une question Python).

    V6.8.1 §12/§26 : extra=forbid — c'est un contrat de FAITS
    (progression observée), JAMAIS de décision : décider est le
    rôle du Learning Engine V7 (LearningDecision, à part).
    """

    model_config = {"extra": "forbid"}

    status: Literal["active", "not_started", "unavailable"] = (
        Field(
            default="not_started",
            description="active : données d'apprentissage "
            "disponibles ; not_started : étudiant/matière/topic "
            "sans observation (§26-§28) ; unavailable : erreur "
            "de lecture (fallback silencieux)",
        )
    )
    subject: str | None = None
    topic: str | None = None
    mastery: float | None = Field(default=None, ge=0.0, le=1.0)
    attempts: int = 0
    strengths: list[str] = Field(default_factory=list)
    weak_points: list[str] = Field(default_factory=list)
    last_assessed_at: str | None = None
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    subject_mastery: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    goal: LearningGoal | None = None

    # ----------------------------------------------------------
    # V6.8.1 §20 — SHIM DE TRANSITION (lecture dict historique).
    # BuiltContext.learning est TYPÉE depuis V6.8.1 ; les
    # consommateurs legacy accèdent encore via ["status"] /
    # .get("mastery") comme au temps du dict. Ces deux méthodes
    # maintiennent la compat sans dupliquer le contrat — à
    # retirer quand tous les consommateurs sont migrés vers les
    # attributs (une entrée de dette dédiée suit la migration).
    # ----------------------------------------------------------

    def __getitem__(self, key: str):
        """Accès dict historique : info["status"] (transition)."""
        if not hasattr(self, key):
            raise KeyError(key)
        return getattr(self, key)

    def get(self, key: str, default=None):
        """Accès dict historique : info.get("mastery")."""
        if not hasattr(self, key):
            return default
        return getattr(self, key)


__all__ = [
    "TopicLearningState",
    "SubjectLearningState",
    "LearningGoal",
    "LearningObservation",
    "LearningProfile",
    "LearningContextInfo",
    "OBSERVATION_SOURCES",
]
