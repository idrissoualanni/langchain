# Learning Rules V7 — règles pédagogiques DÉTERMINISTES (§10-§14/§22).
#
# Le moteur est testable/prévisible/explicable (§21) : aucune
# heuristique cachée, chaque seuil est une CONSTANTE NOMMÉE
# documentée ici. Pas de ML (§11), pas de LLM dans la décision.
#
# Sources de données (V6.8.1 — BuiltContext canonique) :
#   context.learning  : LearningContextInfo (mastery, attempts,
#                       confidence, weak_points, strengths, goal,
#                       last_assessed_at, status)
#   context.routing   : status/subject/topic/candidates
#   context.knowledge : SearchResponse (found/insufficient/...)
#   context.fallback  : FallbackDecision V6.6
#   context.activity  : ActivityContextInfo (thread-local §50)
from __future__ import annotations

from datetime import datetime, timezone

# ------------------------------------------------------------------
# §12 — Zones de maîtrise (paramètres pédagogiques centralisés)
# ------------------------------------------------------------------
# Basées sur le mastery learning : en dessous de 0.40 la production
# est dépendante de l'aide (weak) ; 0.40-0.69 l'étudiant produit
# avec soutien (developing) ; 0.70-0.84 il produit seul de façon
# fiable mais pas encore fluide (proficient) ; ≥0.85 la maîtrise
# est consolidée (strong). Les bornes sont INCLUSIVES en bas.
MASTERY_THRESHOLDS = {
    "weak": 0.40,        # [0.00, 0.40) → weak
    "developing": 0.70,  # [0.40, 0.70) → developing
    "proficient": 0.85,  # [0.70, 0.85) → proficient
    "strong": 1.01,      # [0.85, 1.00] → strong
}


def mastery_zone(mastery: float | None) -> str:
    """Zone de maîtrise §12 — None → 'unknown' (pas inventé)."""
    if mastery is None:
        return "unknown"
    if mastery < MASTERY_THRESHOLDS["weak"]:
        return "weak"
    if mastery < MASTERY_THRESHOLDS["developing"]:
        return "developing"
    if mastery < MASTERY_THRESHOLDS["proficient"]:
        return "proficient"
    return "strong"


# ------------------------------------------------------------------
# §13 — Confiance de l'estimation
# ------------------------------------------------------------------
# Confidence basse = l'estimation mastery n'est pas fiable : on ne
# progresse pas de topic sur une estimation incertaine — on confirme
# d'abord (practice/evaluate). Seuils alignés sur CONFIDENCE_GAIN
# de learning_profile (0.24 à 1 obs, 0.48 à 3, 0.73 à 10).
CONFIDENCE_LOW = 0.40    # < 0.40 → estimation peu fiable
CONFIDENCE_HIGH = 0.70   # ≥ 0.70 → estimation fiable

# Tentatives minimales avant de faire avancer un topic : 2 essais
# fiables valent mieux qu'une réussite isolée (§10).
MIN_ATTEMPTS_TO_ADVANCE = 2


# ------------------------------------------------------------------
# §11 — Trajectoire (progression / régression / plateau)
# ------------------------------------------------------------------
# Lue sur l'historique des observations (list_observations §33 du
# Profile) : les N derniers scores. PAS de ML : règles simples.
TRAJECTORY_WINDOW = 3          # derniers scores analysés
TRAJECTORY_MIN_DELTA = 0.02    # pente min. significative par score
                              # (2 pts/évaluation : 0.70→0.69→0.65
                              # = −0.025/pas → régression §11 ;
                              # 0.50→0.52→0.51 = +0.005 → plateau)
TRAJECTORY_STALE_DAYS = 14     # §35 : topic non évalué depuis N jours


def read_trajectory(scores: list[float | None]) -> str:
    """Trajectoire §11 depuis les derniers scores.

    - 'progression' : pente moyenne > +delta sur la fenêtre
    - 'regression'  : pente moyenne < -delta
    - 'plateau'      : |pente| ≤ delta (stable)
    - 'unknown'      : moins de 2 scores exploitables
    Les None (observations non scorées) sont ignorés.
    """
    vals = [s for s in scores if s is not None]
    if len(vals) < 2:
        return "unknown"
    vals = vals[-TRAJECTORY_WINDOW:]
    if len(vals) < 2:
        return "unknown"
    deltas = [
        vals[i + 1] - vals[i] for i in range(len(vals) - 1)
    ]
    slope = sum(deltas) / len(deltas)
    if slope > TRAJECTORY_MIN_DELTA:
        return "progression"
    if slope < -TRAJECTORY_MIN_DELTA:
        return "regression"
    return "plateau"


def is_stale(last_assessed_at: str | None) -> bool:
    """§35 : topic non évalué depuis TRAJECTORY_STALE_DAYS jours
    (révision simple, pas de spaced repetition complète)."""
    if not last_assessed_at:
        return False
    try:
        last = datetime.fromisoformat(last_assessed_at)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        age_days = (
            datetime.now(timezone.utc) - last
        ).days
        return age_days >= TRAJECTORY_STALE_DAYS
    except Exception:
        return False


# ------------------------------------------------------------------
# §22 — Pondérations du score de priorité (constantes nommées)
# ------------------------------------------------------------------
# priority = somme des poids des signaux ACTIFS (0..10). Ordre
# relatif des règles en conflit (§43) — pas un seuil absolu.
W_CURRENT_ACTIVITY = 10   # §8/§33 : l'activité courante PRIME
W_ACTIVE_GOAL = 4         # §15 : goal actif oriente, n'impose pas
W_WEAK_POINT = 5          # §14 : faiblesse observée récemment
W_LOW_MASTERY = 4         # §12 : zone weak
W_REGRESSION = 5          # §11 : trajectoire descendante
W_LOW_CONFIDENCE = 3      # §13 : estimation peu fiable
W_STALE_TOPIC = 2         # §35 : révision espacée simple


def score_priority(
    *,
    has_current_activity: bool = False,
    has_active_goal: bool = False,
    has_weak_points: bool = False,
    mastery_zone_: str = "unknown",
    trajectory: str = "unknown",
    confidence: float | None = None,
    stale: bool = False,
) -> int:
    """Score de priorité agrégé §22 (déterministe, testable)."""
    p = 0
    if has_current_activity:
        p += W_CURRENT_ACTIVITY
    if has_weak_points:
        p += W_WEAK_POINT
    if trajectory == "regression":
        p += W_REGRESSION
    if mastery_zone_ == "weak":
        p += W_LOW_MASTERY
    if confidence is not None and confidence < CONFIDENCE_LOW:
        p += W_LOW_CONFIDENCE
    if has_active_goal:
        p += W_ACTIVE_GOAL
    if stale:
        p += W_STALE_TOPIC
    return min(10, p)


# ------------------------------------------------------------------
# §16 — Disponibilité knowledge (réalisabilité de la stratégie)
# ------------------------------------------------------------------
def knowledge_available(status: str) -> bool:
    """Une stratégie fondée sur le cours est-elle réalisable ?

    found → oui ; insufficient/unavailable/error → non (le
    moteur ne fait PAS de recherche lui-même §17 — il s'appuie
    sur le fallback V6.6 déjà décidé).
    """
    return status == "found"


__all__ = [
    "MASTERY_THRESHOLDS",
    "mastery_zone",
    "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH",
    "MIN_ATTEMPTS_TO_ADVANCE",
    "TRAJECTORY_WINDOW",
    "TRAJECTORY_MIN_DELTA",
    "TRAJECTORY_STALE_DAYS",
    "read_trajectory",
    "is_stale",
    "W_CURRENT_ACTIVITY",
    "W_ACTIVE_GOAL",
    "W_WEAK_POINT",
    "W_LOW_MASTERY",
    "W_REGRESSION",
    "W_LOW_CONFIDENCE",
    "W_STALE_TOPIC",
    "score_priority",
    "knowledge_available",
]
