# Text Scoring (Phase 2) — helpers de scoring déterministe CANONIQUES.
#
# Extraits de pedagogical_tools (V5.2) pour être partagés entre le
# Evaluation Engine (§19 « deterministic ») et les tools pédagogiques
# SANS duplication : pedagogical_tools ré-importe ces fonctions ici.
# Une seule source de vérité pour le vocabulaire de scoring.
from __future__ import annotations

import re
import unicodedata

# Mots trop courants retirés du scoring d'évaluation (identiques
# à la liste V5.2 historique — ne pas éditer sans migration).
EVAL_STOP_WORDS = {
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "ou",
    "en", "dans", "pour", "par", "sur", "est", "sont", "avec", "que",
    "qui", "quoi", "ce", "cet", "cette", "ces", "aux", "au", "a",
    "plus", "moins", "très", "tres", "peut", "être", "etre", "comme",
    "the", "is", "are", "of", "and", "or", "to", "in", "it",
}


def strip_accents(text: str) -> str:
    """Normalise le texte sans accents (comparaison insensible)."""
    return "".join(
        ch
        for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )


def key_terms(content: str, max_terms: int = 6) -> list[str]:
    """Termes-clés d'une section knowledge : mots signifiants les plus
    longs (heuristic : le vocabulaire technique est le plus long)."""
    raw = re.findall(r"[a-z0-9]{4,}", strip_accents(content.lower()))
    counts: dict[str, int] = {}
    for w in raw:
        if w in EVAL_STOP_WORDS:
            continue
        counts[w] = counts.get(w, 0) + 1
    ranked = sorted(
        counts, key=lambda w: len(w) * (1 + counts[w]), reverse=True
    )
    return ranked[:max_terms]


def content_tokens(content: str) -> set[str]:
    """Tokens signifiants d'un contenu (3+ chars, sans stop words)."""
    return {
        w
        for w in re.findall(r"[a-z0-9]{3,}", strip_accents(content.lower()))
        if w not in EVAL_STOP_WORDS
    }


def score_course_answer(content: str, answer: str) -> tuple[float, list[str], list[str]]:
    """Score déterministe d'une réponse vs le contenu de cours (§19).

    Formule historique V5.2 (inchangée, garanti non-régression) :
      score = 0.7 * couverture des key_terms + 0.3 * richesse
    Richesse = tokens (3+) du cours présents dans la réponse, bornée
    à 20 tokens de référence.

    Retourne (score [0..1], covered, missing).
    """
    content_tok = content_tokens(content or "")
    answer_tok = content_tokens(answer or "")
    terms = key_terms(content or "", max_terms=6)

    covered = [t for t in terms if t in answer_tok]
    missing = [t for t in terms if t not in answer_tok]
    coverage = len(covered) / max(1, len(terms))

    overlap = content_tok & answer_tok
    richness = (
        len(overlap) / min(20, len(content_tok)) if content_tok else 0.0
    )

    score = round(0.7 * coverage + 0.3 * min(1.0, richness), 2)
    return score, covered, missing


__all__ = [
    "EVAL_STOP_WORDS",
    "strip_accents",
    "key_terms",
    "content_tokens",
    "score_course_answer",
]