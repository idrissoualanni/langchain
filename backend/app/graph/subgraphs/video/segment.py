# VideoSubgraph — SERVICE SEGMENTATION pédagogique.
#
# Équivaut, EN DOSSIER, au service `video_segment.py` décrit par le
# plan (segmentation pédagogique du transcript + validation Pydantic +
# persistance). Le fichier original est absent du dépôt à l'audit
# (RAPPORT-AUDIT-MASTER-PLAN : « fichier amorcé absent »).
#
# Segmentation DÉTERMINISTE :
#   split_sentences      → découpe phrases/lignes ;
#   _group_sentences     → regroupement par volume de mots cible ;
#   _timestamps          → bornes [start, end] (interpolation linéaire
#                          sur la durée ; repli 1 s/mot si durée nulle) ;
#   extract_topics       → sujets dominants (fréquence, tri stable) ;
#   segment_transcript   → segments validés Pydantic (PedagogicalSegment).
#
# Aucun LLM, aucun réseau : purement déterministe et testable.
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from app.graph.subgraphs.video.schemas import PedagogicalSegment

_SENTENCE_RE = re.compile(r"\s*\n+\s*|(?<=[.!?…])\s+")
_WORD_RE = re.compile(r"[a-zA-ZÀ-ÿà-ÿ0-9]+")

# Stop-words FR/EN + vocabulaire pédagogique de bruit (les « fonctions »
# sont déjà le thème : ne discriminent pas les segments).
_STOPWORDS = {
    "le", "la", "les", "de", "des", "du", "d", "un", "une", "et", "ou",
    "que", "qui", "quoi", "pour", "avec", "dans", "par", "sur", "est",
    "sont", "son", "ses", "ce", "cet", "cette", "ces", "en", "au", "aux",
    "à", "ne", "pas", "plus", "moins", "très", "si", "nous", "vous",
    "ils", "elles", "on", "leur", "leurs", "the", "and", "is", "are",
    "of", "to", "in", "for", "on", "with", "from", "by", "at", "this",
    "that", "vous", "merci", "bonne", "finalement", "enfin", "toujours",
    "bienvenue", "cours", "vidéo", "explication", "exemples",
    "fonction", "fonctions", "python", "code", "mot", "clé", "mot-clé",
    "tâche", "valeurs", "cas", "ainsi", "même", "dans", "vérifier",
}


class SegmentationError(Exception):
    """Erreur contrôlée de segmentation (transcript vide/invalide)."""


def split_sentences(text: str) -> list[str]:
    """Découpe le transcript en phrases (sauts de ligne = phrases)."""
    if not text or not text.strip():
        return []
    return [p.strip() for p in _SENTENCE_RE.split(text) if p and p.strip()]


def _word_count(text: str) -> int:
    return len(_WORD_RE.findall(text))


def _words(text: str) -> list[str]:
    return _WORD_RE.findall((text or "").lower())


def extract_topics(text: str, top_n: int = 3) -> list[str]:
    """Sujets dominants d'un texte (fréquence, tri stable)."""
    words = [
        w
        for w in _words(text)
        if len(w) >= 3 and w not in _STOPWORDS and not w.isdigit()
    ]
    freq = Counter(words)
    ranked = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    return [word for word, _count in ranked[: max(1, top_n)]]


def _group_sentences(sentences: list[str], target_words: int) -> list[list[str]]:
    """Regroupe les phrases en segments ≃ target_words mots chacun."""
    groups: list[list[str]] = []
    current: list[str] = []
    count = 0
    for sentence in sentences:
        w = _word_count(sentence)
        if count > 0 and count + w > target_words:
            groups.append(current)
            current = [sentence]
            count = w
        else:
            current.append(sentence)
            count += w
    if current:
        groups.append(current)
    return groups or [[]]


def _timestamps(word_counts: list[int], total_duration: float) -> list[tuple[float, float]]:
    """Bornes [start, end] par interpolation linéaire de la durée.

    La durée est répartie proportionnellement au nombre de mots de
    chaque segment. Si durée inconnue (0), repli 1 seconde par mot.
    """
    total = sum(word_counts) or 1
    if total_duration <= 0:
        total_duration = float(total)
    bounds: list[tuple[float, float]] = []
    elapsed = 0.0
    for wc in word_counts:
        seg_dur = (wc / total) * total_duration
        bounds.append((round(elapsed, 2), round(elapsed + seg_dur, 2)))
        elapsed += seg_dur
    return bounds


def segment_parts(
    transcript: str,
    *,
    duration: float = 0.0,
    target_words: int = 90,
    max_segments: int = 20,
    topics_per_segment: int = 2,
) -> list[dict]:
    """Segmente en paires {segment, text}.

    `segment` est un dict Pydantic-VALIDÉ (PedagogicalSegment) exporté
    par le contrat ; `text` est la transcription brute du groupe
    (réservée au retrieval : jamais exposée dans VideoResult.segments).
    """
    text = (transcript or "").strip()
    if not text:
        raise SegmentationError("transcript vide : segmentation impossible")

    sentences = split_sentences(text)
    groups = _group_sentences(sentences, target_words)[:max_segments]
    word_counts = [_word_count(" ".join(g)) for g in groups]
    bounds = _timestamps(word_counts, float(duration or 0.0))

    parts: list[dict] = []
    for index, (group, (start, end)) in enumerate(zip(groups, bounds)):
        group_text = " ".join(group)
        first_sentence = group[0] if group else group_text
        summary = first_sentence[:140]
        if len(first_sentence) > 140:
            summary += "…"
        topics = extract_topics(group_text, top_n=topics_per_segment)
        leading = (topics[0] if topics else "").capitalize()
        title = "Introduction" if index == 0 else (leading or "Suite")
        try:
            segment = PedagogicalSegment(
                title=title,
                summary=summary,
                start=start,
                end=end,
                topics=topics,
            )
        except Exception as exc:  # pragma: no cover — défensif
            raise SegmentationError(
                f"segment invalide ({index}): {exc}"
            ) from exc
        parts.append({"segment": segment.model_dump(), "text": group_text})

    return parts


def segment_transcript(
    transcript: str,
    *,
    duration: float = 0.0,
    target_words: int = 90,
    max_segments: int = 20,
    topics_per_segment: int = 2,
) -> list[dict]:
    """Segmente le transcript en segments pédagogiques VALIDÉS Pydantic.

    Retourne une liste de PedagogicalSegment.model_dump() :
    [{title, summary, start, end, topics}].
    """
    return [
        p["segment"]
        for p in segment_parts(
            transcript,
            duration=duration,
            target_words=target_words,
            max_segments=max_segments,
            topics_per_segment=topics_per_segment,
        )
    ]


def persist_segments(segments: list[dict], path: str) -> str:
    """Persiste les segments au format JSON (validation Pydantic)."""
    validated = [
        PedagogicalSegment(**s).model_dump() for s in segments
    ]
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(validated, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return str(target)


def load_segments(path: str) -> list[dict]:
    """Recharge des segments précédemment persistés (validation)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [PedagogicalSegment(**s).model_dump() for s in raw]


__all__ = [
    "SegmentationError",
    "extract_topics",
    "load_segments",
    "persist_segments",
    "segment_parts",
    "segment_transcript",
    "split_sentences",
]