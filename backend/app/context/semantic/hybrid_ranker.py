# Hybrid Ranking V7.1 (mission §10/§11/§13).
#
# NE SUPPRIME PAS le lexical (§10) : le score final combine
#   final = LEXICAL_WEIGHT * lexical_score
#         + SEMANTIC_WEIGHT * semantic_score
# avec des PONDÉRATIONS NOMMÉES, CENTRALISÉES, TESTABLES,
# DOCUMENTÉES (ci-dessous) — modifiables sans réécrire
# l'algorithme (set_hybrid_weights / reset_hybrid_weights).
#
# JUSTIFICATION DES POIDS (§10 : pas de coefficient arbitraire) :
#   LEXICAL 0.45 — le lexical est DÉTERMINISTE et de haute
#     précision (alias plein = 2.0 normalisé à 1.0) ; il prime
#     légèrement car un match exact d'alias/topic est une preuve
#     plus forte qu'une similarité d'embedding ;
#   SEMANTIC 0.55 — la couche sémantique apporte la couverture
#     (paraphrases, descriptions conceptuelles) que le lexical
#     ne peut pas attraper ; à qualité égale de provider, la
#     similarité 0.8+ sur les candidats riches est très
#     discriminante. La somme > 0.5 donne à la sémantique un
#     avantage marginal REFLETANT son rôle de recall, sans
#     écraser la précision lexicale.
#
# CANDIDATS (§11) : plusieurs candidats conservés AVANT décision ;
# la décision utilise top score, ÉCART entre candidats, confiance,
# ambiguïté — jamais « premier du YAML ».
from __future__ import annotations

import threading
from dataclasses import dataclass, field

from app.logging.events import log_event

# --- Pondérations centralisées (§10) ------------------------------
LEXICAL_WEIGHT = 0.45
SEMANTIC_WEIGHT = 0.55

# Écart minimal entre top-1 et top-2 pour trancher (§11/§13) :
# en dessous, les deux candidats sont aussi bons l'un que l'autre
# → ambiguous (jamais un choix arbitraire).
# 0.10 : calibré sur mesures réelles qwen3-embedding:0.6b —
# vrai conflit inter-matières mesuré ≤ 0.09 ; concepts distincts
# bien séparés ≥ 0.12.
AMBIGUITY_MARGIN = 0.10

# Margin pour départager deux TOPICS de la MÊME matière (§9) :
# les topics d'un sujet sont proches par construction (même
# matière → même vocabulaire) ; un écart topic trop faible
# signifie « même zone » — on garde le top SANS rétrograder.
# 0.04 : boucles vs loops ≈ 0.02 (même concept, dédupliqué en
# amont) ; return vs fonctions ≈ 0.12 (concepts distincts).
TOPIC_MARGIN = 0.04

# Score hybride minimal pour qu'un candidat soit exploitable.
HYBRID_MIN_SCORE = 0.30

_weights_lock = threading.RLock()
_weights: dict[str, float] = {
    "lexical": LEXICAL_WEIGHT,
    "semantic": SEMANTIC_WEIGHT,
    "ambiguity_margin": AMBIGUITY_MARGIN,
    "hybrid_min_score": HYBRID_MIN_SCORE,
}


def set_hybrid_weights(
    lexical: float | None = None,
    semantic: float | None = None,
    ambiguity_margin: float | None = None,
    hybrid_min_score: float | None = None,
) -> None:
    """Remplace les pondérations SANS toucher l'algorithme (§10).

    Utilisé par les tests ; aussi par l'ops pour régler le
    lexical/semantic selon la qualité réelle du provider.
    """
    with _weights_lock:
        if lexical is not None:
            _weights["lexical"] = float(lexical)
        if semantic is not None:
            _weights["semantic"] = float(semantic)
        if ambiguity_margin is not None:
            _weights["ambiguity_margin"] = float(ambiguity_margin)
        if hybrid_min_score is None:
            pass
        else:
            _weights["hybrid_min_score"] = float(hybrid_min_score)


def reset_hybrid_weights() -> None:
    """Retour aux valeurs documentées par défaut."""
    with _weights_lock:
        _weights.update(
            {
                "lexical": LEXICAL_WEIGHT,
                "semantic": SEMANTIC_WEIGHT,
                "ambiguity_margin": AMBIGUITY_MARGIN,
                "hybrid_min_score": HYBRID_MIN_SCORE,
            }
        )


def get_hybrid_weights() -> dict[str, float]:
    with _weights_lock:
        return dict(_weights)


@dataclass
class RankedCandidate:
    """UN candidat hybride (subject/topic + scores + type)."""

    subject: str
    topic: str | None
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    final_score: float = 0.0
    # exact / lexical / morphological / semantic / hybrid (§9)
    match_type: str = "hybrid"

    def as_dict(self) -> dict:
        return {
            "subject": self.subject,
            "topic": self.topic,
            "score": round(self.final_score, 4),
            "lexical_score": round(self.lexical_score, 4),
            "semantic_score": round(self.semantic_score, 4),
            "match_type": self.match_type,
        }


@dataclass
class HybridRankingOutcome:
    """Résultat du ranking — candidats conservés (§11).

    ambiguous=True → top-1 et top-2 trop proches : le
    consommateur (router) DOIT produire status=ambiguous.
    """

    candidates: list[RankedCandidate] = field(default_factory=list)
    ambiguous: bool = False
    margin: float = 0.0
    best: RankedCandidate | None = None

    def as_dicts(self, limit: int = 5) -> list[dict]:
        return [c.as_dict() for c in self.candidates[:limit]]


def _match_type_for(
    lexical: float, semantic: float
) -> str:
    """match_type §9 : quelle couche a porté le candidat ?"""
    if lexical >= 0.999:
        return "exact"
    if lexical >= 0.4 and semantic >= 0.3:
        return "hybrid"
    if lexical >= 0.4:
        return "lexical"
    if semantic >= 0.3:
        return "semantic"
    return "hybrid"


def rank_candidates(
    lexical_candidates: list[dict],
    semantic_candidates: list[dict],
    query: str = "",
    semantic_status: str = "available",
    user_id: str = "",
    thread_id: str = "",
) -> HybridRankingOutcome:
    """Hybrid ranking §10/§11 — combine et départage.

    Entrées :
      lexical_candidates  : [{subject, topic, score, match_kind}]
                            (score normalisé [0..1] par l'appelant)
      semantic_candidates : [{subject, topic, score}] (cosine [0..1])
      semantic_status     : available/unavailable/error — si !=
                            available, la part sémantique vaut 0
                            (lexical fallback, §15)

    Sortie : candidats triés par final_score DESC, ambiguïté
    détectée par écart top-1/top-2 (§13).
    """
    with _weights_lock:
        w_lex = _weights["lexical"]
        w_sem = _weights["semantic"]
        margin = _weights["ambiguity_margin"]
        min_score = _weights["hybrid_min_score"]

    sem_by_key: dict[tuple[str, str | None], float] = {}
    if semantic_status == "available":
        for c in semantic_candidates:
            key = (c.get("subject", ""), c.get("topic") or None)
            prev = sem_by_key.get(key, 0.0)
            sem_by_key[key] = max(prev, float(c.get("score", 0.0)))

    lex_by_key: dict[tuple[str, str | None], dict] = {}
    for c in lexical_candidates:
        key = (c.get("subject", ""), c.get("topic") or None)
        prev = lex_by_key.get(key)
        if prev is None or float(c.get("score", 0.0)) > float(
            prev.get("score", 0.0)
        ):
            lex_by_key[key] = c

    keys = set(lex_by_key) | set(sem_by_key)
    ranked: list[RankedCandidate] = []
    for key in keys:
        lex_c = lex_by_key.get(key)
        lex_s = float(lex_c.get("score", 0.0)) if lex_c else 0.0
        sem_s = sem_by_key.get(key, 0.0)
        final = w_lex * lex_s + w_sem * sem_s
        if final <= 0:
            continue
        ranked.append(
            RankedCandidate(
                subject=key[0],
                topic=key[1],
                lexical_score=lex_s,
                semantic_score=sem_s,
                final_score=final,
                match_type=_match_type_for(lex_s, sem_s),
            )
        )

    ranked.sort(key=lambda c: c.final_score, reverse=True)
    ranked = [c for c in ranked if c.final_score >= min_score] or ranked[:3]

    outcome = HybridRankingOutcome(candidates=ranked)
    if ranked:
        outcome.best = ranked[0]
        if len(ranked) > 1:
            gap = ranked[0].final_score - ranked[1].final_score
            outcome.margin = round(gap, 4)
            # AMBIGUÏTÉ = seulement si les 2 meilleurs candidats
            # portent sur des MATIÈRES DISTINCTES (§13) — deux
            # topics de la même matière ne sont pas une ambiguïté
            # de routing (choix du topic, pas de la matière).
            subjects_distinct = (
                ranked[1].subject != ranked[0].subject
            )
            outcome.ambiguous = (
                subjects_distinct and gap < margin
            )

    log_event(
        "HYBRID_RANKING",
        message=(
            f"Hybrid ranking | candidates={len(ranked)} | "
            f"ambiguous={outcome.ambiguous} | "
            f"margin={outcome.margin}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        extra={
            "operation": "hybrid_ranking",
            "query": (query or "")[:100],
            "candidates": outcome.as_dicts(5),
            "ambiguous": outcome.ambiguous,
            "margin": outcome.margin,
            "semantic_status": semantic_status,
            "weights": {"lexical": w_lex, "semantic": w_sem},
        },
    )
    return outcome


__all__ = [
    "LEXICAL_WEIGHT",
    "SEMANTIC_WEIGHT",
    "AMBIGUITY_MARGIN",
    "HYBRID_MIN_SCORE",
    "RankedCandidate",
    "HybridRankingOutcome",
    "rank_candidates",
    "set_hybrid_weights",
    "reset_hybrid_weights",
    "get_hybrid_weights",
]
