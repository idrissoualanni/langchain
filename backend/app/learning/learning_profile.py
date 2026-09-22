# Learning Profile V6 — persistance + Profile Updater (§14).
#
# Stockage : SqliteStore EXISTANT (aucune nouvelle technologie,
# §5 Option A) sous namespace distinct de User Memory (§6) :
#
#   User Memory       ("users", "profile", user_id) clés facts/profile
#   Learning Profile  ("users", "learning", user_id) clés
#                     profile / observations / goals_seq
#
# Le Learning Profile est CROSS-THREAD (§4) : jamais de thread_id
# dans le namespace. Il ne contient AUCUN message (§34).
#
# Séparation observation / profil (§13) :
#   Exercise → evaluate_answer → LearningObservation (§12)
#           → update_profile_from_observation (ICI)
#           → intégration DÉTERMINISTE documentée (§15)
from __future__ import annotations

import uuid

from app.agent.memory import _store_lock, get_store
from app.schemas.learning import (
    LearningGoal,
    LearningObservation,
    LearningProfile,
    SubjectLearningState,
    TopicLearningState,
)
from app.logging.events import log_event

NAMESPACE_LABEL = "users/learning"

# --- Budget historique (§33) : on garde les N dernières
# observations par profil — assez pour retracer l'évolution du
# mastery, sans croître indéfiniment.
MAX_OBSERVATIONS = 50

# --- Poids par source (§10 : les observations ne se valent pas).
# assessment/teacher_feedback = jugement expert (poids plein) ;
# exercise = auto-évaluée par le scoring des réponses (légère
# décote, le scoring lexical peut se tromper) ; quiz = pondéré
# pareil qu'exercise (même nature).
SOURCE_WEIGHTS = {
    "assessment": 1.0,
    "teacher_feedback": 1.0,
    "exercise": 0.8,
    "quiz": 0.8,
}

# --- Formule d'évolution du mastery (§15) — SIMPLE et DÉTERMINISTE.
#    new = old * (1 - w) + score * w     avec w = poids effectif
#    w = OBSERVATION_WEIGHT * source_weight * observation.confidence
#
# POURQUOI cette forme : moyenne mobile exponentielle pondérée.
#   - L'ancienne estimation n'est JAMAIS écrasée (§33) : elle
#     garde 70% de poids pour une observation exercise standard.
#   - Une observation fiable (assessment, confidence 1.0) pèse
#     jusqu'à 30% ; un feedback lexical incertain pèse moins.
#   - Converge vers le niveau réel en quelques observations,
#     absorbe un accident (un mauvais exercice ne détruit pas
#     un profil solide).
# PAS de ML (§15) : deux constantes, testables, expliquées.
OBSERVATION_WEIGHT = 0.3

# --- Confiance de l'estimation (§9) : croît avec le nombre
# d'observations (vitesse décroissante, asymptote 0.95) :
#    confidence = 0.95 * attempts / (attempts + 3)
# 1 observation → 0.24 (peu sûr), 3 → 0.48, 10 → 0.73.
CONFIDENCE_GAIN = 0.95
CONFIDENCE_HALFLIFE = 3.0


def _learning_namespace(user_id: str) -> tuple[str, ...]:
    """Namespace Learning Profile (§6) — distinct de User Memory."""
    return ("users", "learning", user_id)


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------------
# Lecture / écriture brutes (toujours sous _store_lock, cf. memory.py)
# ------------------------------------------------------------------


def read_learning_profile(user_id: str) -> LearningProfile | None:
    """Charge le profil learning — None s'il n'existe pas (§26).

    Émet LEARNING_PROFILE_READ. L'absence de profil N'EST PAS une
    erreur : nouvel étudiant = cas normal.
    """
    try:
        with _store_lock:
            store = get_store()
            item = store.get(_learning_namespace(user_id), "profile")
        if item is None or not item.value:
            log_event(
                "LEARNING_PROFILE_READ",
                message=(
                    f"Learning profile absent | user={user_id}"
                ),
                user_id=user_id,
                extra={
                    "operation": "learning_profile_read",
                    "namespace": NAMESPACE_LABEL,
                    "found": False,
                },
            )
            return None

        profile = LearningProfile.model_validate(item.value)
        log_event(
            "LEARNING_PROFILE_READ",
            message=(
                f"Learning profile read | user={user_id} | "
                f"subjects={len(profile.subjects)} | "
                f"goals={len(profile.goals)}"
            ),
            user_id=user_id,
            extra={
                "operation": "learning_profile_read",
                "namespace": NAMESPACE_LABEL,
                "found": True,
                "subjects": list(profile.subjects.keys()),
            },
        )
        return profile
    except Exception as exc:
        # §26 : ne jamais faire échouer un run pour le profil —
        # l'erreur est loggée, le tuteur continue sans learning.
        log_event(
            "LEARNING_PROFILE_READ",
            level="ERROR",
            message=f"Learning profile read error: {exc}",
            user_id=user_id,
            extra={
                "operation": "learning_profile_read",
                "error": str(exc)[:300],
            },
        )
        return None


def write_learning_profile(profile: LearningProfile) -> LearningProfile:
    """Persiste le profil learning. Émet LEARNING_PROFILE_WRITE."""
    profile.updated_at = _now()
    with _store_lock:
        store = get_store()
        store.put(
            _learning_namespace(profile.user_id),
            "profile",
            profile.model_dump(),
        )
    log_event(
        "LEARNING_PROFILE_WRITE",
        message=(
            f"Learning profile saved | user={profile.user_id} | "
            f"subjects={len(profile.subjects)}"
        ),
        user_id=profile.user_id,
        extra={
            "operation": "learning_profile_write",
            "namespace": NAMESPACE_LABEL,
        },
    )
    return profile


def _append_observation(
    user_id: str, observation: LearningObservation
) -> None:
    """Historique minimal des observations (§33) — clé séparée.

    N dernières (FIFO) : permet de retracer l'évolution du
    mastery, sans écraser l'historique à chaque update.
    """
    with _store_lock:
        store = get_store()
        item = store.get(
            _learning_namespace(user_id), "observations"
        )
        history: list[dict] = (
            list(item.value) if item and item.value else []
        )
        history.append(observation.model_dump())
        history = history[-MAX_OBSERVATIONS:]
        store.put(
            _learning_namespace(user_id),
            "observations",
            history,
        )


def list_observations(
    user_id: str, subject: str | None = None, topic: str | None = None
) -> list[dict]:
    """Historique des observations (filtrable subject/topic)."""
    with _store_lock:
        store = get_store()
        item = store.get(
            _learning_namespace(user_id), "observations"
        )
    history: list[dict] = (
        list(item.value) if item and item.value else []
    )
    if subject:
        history = [o for o in history if o.get("subject") == subject]
    if topic:
        history = [o for o in history if o.get("topic") == topic]
    return history


# ------------------------------------------------------------------
# Validation Registry (§18) — jamais de subject/topic inventé
# ------------------------------------------------------------------


def validate_observation_targets(
    subject: str, topic: str | None = None
) -> tuple[bool, str]:
    """Vérifie que subject/topic existent dans le Subject Registry.

    Retourne (ok, message). Une faute de frappe (« pythonn ») doit
    être REJETÉE, pas silencieusement créée (§18).
    """
    from app.subjects.registry import get_subject

    cfg = get_subject(subject)
    if cfg is None:
        return (
            False,
            f"Matière inconnue du Subject Registry : '{subject}' "
            "(vérifiez l'orthographe — le profil learning ne crée "
            "pas de matières)",
        )
    if topic and topic not in cfg.topics:
        return (
            False,
            f"Topic '{topic}' inconnu pour la matière "
            f"'{subject}' (topics connus : {cfg.topics})",
        )
    return True, ""


def resolve_registry_topic(
    subject: str, topic: str, source: str | None = None
) -> str | None:
    """Résout un topic quelconque vers un topic Registry valide.

    Contexte (§18 + flux réel) : les tools pédagogiques travaillent
    en topics de SECTION knowledge (ex: `_intro`, `definition` du
    fichier functions.md), alors que le Learning Profile indexe
    les topics du REGISTRY (ex: `functions`, `fonctions`).
    Stratégie de résolution, dans l'ordre :
      1. topic déjà Registry-valide → renvoyé tel quel ;
      2. la source knowledge (ex: informatique/python/functions)
         se termine par un topic Registry (functions) → renvoyé ;
      3. un topic Registry est contenu dans la source (ex:
         source .../fonctions → fonctions) → renvoyé ;
      4. CANONISATION (mission intégration) : la source désigne
         un FICHIER knowledge (ex: python/functions) ; si ce
         fichier porte le nom d'un topic Registry (functions),
         les topics Registry pointant vers le MÊME fichier (ex:
         « fonctions » → functions.md via son titre H1) sont
         canonisés vers le stem (une seule clé de profil par
         fichier : FR et EN convergent) ;
      5. aucun match → None (l'observation sera rejetée §18,
         jamais de topic inventé).
    """
    from app.subjects.registry import get_subject

    cfg = get_subject(subject)
    if cfg is None:
        return None
    if topic in cfg.topics:
        return topic

    src = (source or "").lower()
    if src:
        # .../functions.md → functions
        last = src.rstrip("/").rsplit("/", 1)[-1]
        if last in cfg.topics:
            return last
        # containment (ex: source contient 'fonctions')
        for t in cfg.topics:
            if t and t in src:
                return t
        # canonisation fichier → topic Registry (une seule clé
        # de profil par fichier knowledge : fonctions ≡ functions)
        if last:
            from app.context.knowledge_retriever import (
                resolve_topic_source,
            )

            for t in cfg.topics:
                if t == last:
                    continue
                resolved = resolve_topic_source(subject, t)
                if resolved and resolved[0].endswith(f"/{last}"):
                    return t
    return None


# ------------------------------------------------------------------
# Profile Updater (§14)
# ------------------------------------------------------------------


def _integrate_observation(
    profile: LearningProfile, observation: LearningObservation
) -> LearningProfile:
    """Intègre UNE observation dans le profil — formule §15.

    Mastery (moyenne mobile exponentielle pondérée) :
      w = OBSERVATION_WEIGHT * source_weight * confidence
      new_mastery = old * (1-w) + score * w     (0 si old=None)

    Confidence (§9) : asymptote CONFIDENCE_GAIN sur attempts.
    Subject mastery : agrégat = moyenne des topics pondérée par
    attempts (les topics évalués comptent plus que les vus).
    """
    w_source = SOURCE_WEIGHTS.get(observation.type, 0.8)
    w = OBSERVATION_WEIGHT * w_source * observation.confidence

    subject_id = observation.subject
    topic_id = observation.topic

    subject_state = profile.subjects.get(
        subject_id, SubjectLearningState()
    )
    topic_state = subject_state.topics.get(
        topic_id, TopicLearningState()
    )

    # --- Mastery du topic (§15) ---
    old = topic_state.mastery
    score = observation.score
    if score is not None:
        topic_state.mastery = (
            (old * (1.0 - w) + score * w)
            if old is not None
            else score
        )
    topic_state.attempts += 1
    topic_state.last_assessed_at = observation.created_at

    # --- Strengths / weak_points (§30) : liés à CE topic,
    # dédupliqués, bornés pour ne pas saturer le contexte ---
    for s in observation.strengths:
        if s not in topic_state.strengths:
            topic_state.strengths.append(s)
    topic_state.strengths = topic_state.strengths[-10:]
    for wp in observation.weak_points:
        if wp not in topic_state.weak_points:
            topic_state.weak_points.append(wp)
    topic_state.weak_points = topic_state.weak_points[-10:]

    # --- Confidence de l'estimation (§9) ---
    topic_state.confidence = round(
        CONFIDENCE_GAIN
        * topic_state.attempts
        / (topic_state.attempts + CONFIDENCE_HALFLIFE),
        4,
    )

    subject_state.topics[topic_id] = topic_state

    # --- Agrégat subject (moyenne pondérée par attempts) ---
    assessed = [
        t.mastery
        for t in subject_state.topics.values()
        if t.mastery is not None
    ]
    if assessed:
        weights = [
            t.attempts
            for t in subject_state.topics.values()
            if t.mastery is not None
        ]
        subject_state.mastery = round(
            sum(m * a for m, a in zip(assessed, weights))
            / max(1, sum(weights)),
            4,
        )
    profile.subjects[subject_id] = subject_state
    return profile


def update_profile_from_observation(
    user_id: str,
    observation: LearningObservation,
    thread_id: str = "",
) -> LearningProfile | None:
    """Pipeline complet d'intégration d'une observation (§14).

    1. charge le profil (ou démarre d'un profil neuf §27) ;
    2. valide subject/topic contre le Registry (§18) ;
    3. enregistre l'observation dans l'historique (§33) ;
    4. intègre l'observation (formule §15) ;
    5. sauvegarde ;
    6. journalise LEARNING_OBSERVATION_RECORDED puis
       LEARNING_PROFILE_UPDATE.

    Retourne le profil mis à jour, ou None si la validation
    Registry a rejeté l'observation (loggé WARNING).
    """
    # --- Validation §18 AVANT toute écriture ---
    ok, reason = validate_observation_targets(
        observation.subject, observation.topic
    )
    if not ok:
        log_event(
            "LEARNING_OBSERVATION_RECORDED",
            level="WARNING",
            message=(
                f"Observation rejetée (Registry) | "
                f"user={user_id} | {reason}"
            ),
            user_id=user_id,
            thread_id=thread_id or None,
            extra={
                "operation": "learning_observation_recorded",
                "subject": observation.subject,
                "topic": observation.topic,
                "accepted": False,
                "reason": reason[:200],
            },
        )
        return None

    # --- 1. Chargement (création implicite si premier accès §27) ---
    profile = read_learning_profile(user_id)
    if profile is None:
        profile = LearningProfile(user_id=user_id)

    # --- 3. Historique (§33) ---
    _append_observation(user_id, observation)

    log_event(
        "LEARNING_OBSERVATION_RECORDED",
        message=(
            f"Observation recorded | user={user_id} | "
            f"{observation.subject}/{observation.topic} | "
            f"type={observation.type} | score={observation.score}"
        ),
        user_id=user_id,
        thread_id=thread_id or None,
        extra={
            "operation": "learning_observation_recorded",
            "subject": observation.subject,
            "topic": observation.topic,
            "observation_type": observation.type,
            "score": observation.score,
            "accepted": True,
        },
    )

    # --- 4. Intégration (§15) ---
    profile = _integrate_observation(profile, observation)

    # --- 5. Sauvegarde ---
    write_learning_profile(profile)

    topic_state = profile.subjects[observation.subject].topics[
        observation.topic
    ]
    log_event(
        "LEARNING_PROFILE_UPDATE",
        message=(
            f"Learning profile updated | user={user_id} | "
            f"{observation.subject}/{observation.topic} | "
            f"mastery={topic_state.mastery} | "
            f"attempts={topic_state.attempts} | "
            f"confidence={topic_state.confidence}"
        ),
        user_id=user_id,
        thread_id=thread_id or None,
        extra={
            "operation": "learning_profile_update",
            "subject": observation.subject,
            "topic": observation.topic,
            "mastery": topic_state.mastery,
            "attempts": topic_state.attempts,
            "confidence": topic_state.confidence,
        },
    )
    return profile


# ------------------------------------------------------------------
# Goals (§29) — séparés de la maîtrise
# ------------------------------------------------------------------


def _next_goal_id(profile: LearningProfile) -> str:
    """Compteur monotone par profil (clé goals_seq, §8 exemple)."""
    with _store_lock:
        store = get_store()
        item = store.get(
            _learning_namespace(profile.user_id), "goals_seq"
        )
        seq = (item.value if item and item.value else 0) + 1
        store.put(
            _learning_namespace(profile.user_id), "goals_seq", seq
        )
    return f"goal_{seq}"


def create_learning_goal(
    user_id: str,
    subject: str,
    description: str,
    topic: str | None = None,
    thread_id: str = "",
) -> LearningGoal | None:
    """Crée un objectif d'apprentissage (validé Registry §18)."""
    ok, reason = validate_observation_targets(subject, topic)
    if not ok:
        log_event(
            "LEARNING_GOAL_CREATED",
            level="WARNING",
            message=f"Goal rejeté (Registry) | {reason}",
            user_id=user_id,
            extra={
                "operation": "learning_goal_created",
                "accepted": False,
            },
        )
        return None

    profile = read_learning_profile(user_id)
    if profile is None:
        profile = LearningProfile(user_id=user_id)

    goal = LearningGoal(
        id=_next_goal_id(profile),
        subject=subject,
        topic=topic,
        description=description,
        status="active",
    )
    profile.goals.append(goal)
    write_learning_profile(profile)

    log_event(
        "LEARNING_GOAL_CREATED",
        message=(
            f"Goal created | user={user_id} | {goal.id} | "
            f"{subject}/{topic or '-'} | {description[:80]}"
        ),
        user_id=user_id,
        thread_id=thread_id or None,
        extra={
            "operation": "learning_goal_created",
            "goal_id": goal.id,
            "subject": subject,
            "topic": topic or "",
        },
    )
    return goal


def update_learning_goal(
    user_id: str,
    goal_id: str,
    status: str,
    thread_id: str = "",
) -> LearningGoal | None:
    """Met à jour le statut d'un objectif (active/completed/paused)."""
    if status not in ("active", "completed", "paused"):
        log_event(
            "LEARNING_GOAL_UPDATED",
            level="WARNING",
            message=f"Statut de goal invalide : {status}",
            user_id=user_id,
            extra={
                "operation": "learning_goal_updated",
                "accepted": False,
            },
        )
        return None

    profile = read_learning_profile(user_id)
    if profile is None:
        return None

    goal = next(
        (g for g in profile.goals if g.id == goal_id), None
    )
    if goal is None:
        log_event(
            "LEARNING_GOAL_UPDATED",
            level="WARNING",
            message=f"Goal introuvable : {goal_id}",
            user_id=user_id,
            extra={
                "operation": "learning_goal_updated",
                "accepted": False,
            },
        )
        return None

    goal.status = status
    write_learning_profile(profile)

    log_event(
        "LEARNING_GOAL_UPDATED",
        message=(
            f"Goal updated | user={user_id} | {goal_id} | "
            f"status={status}"
        ),
        user_id=user_id,
        thread_id=thread_id or None,
        extra={
            "operation": "learning_goal_updated",
            "goal_id": goal_id,
            "subject": goal.subject,
            "topic": goal.topic or "",
            "status": status,
        },
    )
    return goal


def get_topic_state(
    user_id: str, subject: str, topic: str
) -> TopicLearningState | None:
    """État d'UN topic — None si le profil n'existe pas (§26/§28).

    Ne CRÉE jamais d'état en lecture : la lecture est sans effet
    de bord. L'état minimal naît à la première observation (§28)
    ou à la première sélection de contexte sur topic connu.
    """
    profile = read_learning_profile(user_id)
    if profile is None:
        return None
    subject_state = profile.subjects.get(subject)
    if subject_state is None:
        return None
    return subject_state.topics.get(topic)


__all__ = [
    "read_learning_profile",
    "write_learning_profile",
    "update_profile_from_observation",
    "list_observations",
    "validate_observation_targets",
    "create_learning_goal",
    "update_learning_goal",
    "get_topic_state",
    "LearningGoal",
    "LearningObservation",
    "LearningProfile",
    "TopicLearningState",
    "SubjectLearningState",
    "NAMESPACE_LABEL",
    "SOURCE_WEIGHTS",
    "OBSERVATION_WEIGHT",
]
