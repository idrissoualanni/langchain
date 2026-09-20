# SemanticRetriever V7.1 (mission §6/§14/§15/§19).
#
# CONTRAT STABLE (Protocol) : le reste du projet (router, tests)
# ne dépend que de search(query, candidates, top_k) →
# SemanticSearchOutcome. L'implémentation est interchangeable
# (une future version ollama/externe implémente le Protocol).
#
# FAIL-SAFE (mission §15/§19) : toute erreur devient l'état
# contrôlé semantic_status="error" — JAMAIS une exception vers le
# pipeline, JAMAIS un faux résultat. L'erreur technique est
# conservée dans SEMANTIC_SEARCH_ERROR (logs), pas transformée en
# score inventé.
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol

from app.context.semantic.candidates import TopicCandidate
from app.context.semantic.provider import (
    cosine_similarity,
    get_embedding_provider,
)
from app.logging.events import log_event

# Statuts de la couche sémantique (mission §19) :
#   available → la recherche a tourné (scores exploitables)
#   unavailable → provider absent/désactivé (pas de tentative)
#   error → exception attrapée → fallback lexical assuré par le
#           consommateur (router)
SEMANTIC_STATUS = ("available", "unavailable", "error")

# Seuil minimal de similarité pour qu'un candidat soit retenu.
SEMANTIC_MIN_SCORE = 0.05


@dataclass
class SemanticMatch:
    """UN candidat scoré sémantiquement."""

    candidate: TopicCandidate
    score: float  # similarité brute [0..1]

    @property
    def subject(self) -> str:
        return self.candidate.subject

    @property
    def topic(self) -> str | None:
        return self.candidate.topic


@dataclass
class SemanticSearchOutcome:
    """Résultat de SemanticRetriever.search — état contrôlé.

    status="available" → matches triés (desc), bornés top_k.
    status="error" → matches=[] + error_loggé (fallback lexical).
    status="unavailable" → matches=[] (provider absent).
    latency_ms : mesure §31 (latence sémantique).
    """

    status: str = "unavailable"
    matches: list[SemanticMatch] = field(default_factory=list)
    latency_ms: int = 0
    error: str = ""

    @property
    def available(self) -> bool:
        return self.status == "available"


class SemanticRetriever(Protocol):
    """Interface métier stable (mission §6)."""

    name: str

    def search(
        self,
        query: str,
        candidates: list[TopicCandidate],
        top_k: int = 5,
    ) -> SemanticSearchOutcome:
        ...


class LocalSemanticRetriever:
    """Retriever sémantique LOCAL (provider embeddings actif).

    Implémentation générique : embed(query) vs embed(candidat),
    cosine, tri, top_k. Cache d'embeddings des candidats (le
    corpus est stable entre les rechargements de registry —
    la requête, elle, est embeddée à chaque appel).
    """

    name = "local-semantic-v1"

    def __init__(self) -> None:
        self._cand_cache: dict[int, list[float]] = {}

    def clear_cache(self) -> None:
        self._cand_cache.clear()

    def _embed_candidate(self, cand: TopicCandidate) -> list[float]:
        key = hash((cand.subject, cand.topic, cand.text))
        emb = self._cand_cache.get(key)
        if emb is None:
            emb = get_embedding_provider().embed_text(cand.text)
            self._cand_cache[key] = emb
        return emb

    def search(
        self,
        query: str,
        candidates: list[TopicCandidate],
        top_k: int = 5,
    ) -> SemanticSearchOutcome:
        start = time.perf_counter()
        log_event(
            "SEMANTIC_SEARCH_START",
            message=f"Semantic search | query={(query or '')[:80]}",
            extra={
                "operation": "semantic_search",
                "query": (query or "")[:100],
                "candidates": len(candidates),
                "provider": get_embedding_provider().name,
            },
        )
        if not candidates:
            outcome = SemanticSearchOutcome(
                status="unavailable",
                latency_ms=_elapsed_ms(start),
                error="no candidates",
            )
            _log_end(outcome, query)
            return outcome
        try:
            provider = get_embedding_provider()
            q_emb = provider.embed_text(query or "")
            matches: list[SemanticMatch] = []
            for cand in candidates:
                score = cosine_similarity(
                    q_emb, self._embed_candidate(cand)
                )
                if score >= SEMANTIC_MIN_SCORE:
                    matches.append(
                        SemanticMatch(candidate=cand, score=score)
                    )
            matches.sort(key=lambda m: m.score, reverse=True)
            matches = matches[: max(1, top_k)]
            outcome = SemanticSearchOutcome(
                status="available",
                matches=matches,
                latency_ms=_elapsed_ms(start),
            )
        except Exception as exc:
            # §15/§19 : état contrôlé, jamais de propagation
            outcome = SemanticSearchOutcome(
                status="error",
                latency_ms=_elapsed_ms(start),
                error=f"{type(exc).__name__}: {exc}",
            )
            log_event(
                "SEMANTIC_SEARCH_ERROR",
                level="ERROR",
                message=f"Semantic search error | cause={outcome.error}",
                extra={
                    "operation": "semantic_search",
                    "query": (query or "")[:100],
                    "status": "error",
                    "error": outcome.error[:200],
                },
            )
        _log_end(outcome, query)
        return outcome

    # compat Protocol attribute
    @property
    def _name(self) -> str:
        return self.name


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _log_end(outcome: SemanticSearchOutcome, query: str) -> None:
    log_event(
        "SEMANTIC_SEARCH_END",
        message=(
            f"Semantic search end | status={outcome.status} | "
            f"matches={len(outcome.matches)} | "
            f"latency={outcome.latency_ms}ms"
        ),
        extra={
            "operation": "semantic_search",
            "query": (query or "")[:100],
            "status": outcome.status,
            "matches": [
                {
                    "subject": m.subject,
                    "topic": m.topic or "",
                    "score": round(m.score, 4),
                }
                for m in outcome.matches[:5]
            ],
            "latency_ms": outcome.latency_ms,
        },
    )
    if outcome.matches:
        log_event(
            "SEMANTIC_CANDIDATES",
            message=(
                "Semantic candidates | "
                + " | ".join(
                    f"{m.candidate.label()}={m.score:.3f}"
                    for m in outcome.matches[:5]
                )
            ),
            extra={
                "operation": "semantic_search",
                "query": (query or "")[:100],
                "candidates": [
                    {
                        "subject": m.subject,
                        "topic": m.topic or "",
                        "score": round(m.score, 4),
                    }
                    for m in outcome.matches[:5]
                ],
            },
        )


# ------------------------------------------------------------------
# Retriever actif — configurable (mission §6 : interchangeable)
# ------------------------------------------------------------------
import threading

_RETRIEVER_LOCK = threading.RLock()
_RETRIEVER: LocalSemanticRetriever | SemanticRetriever | None = None

# Alias public réexporté pour __init__ (evite import circulaire)
RETRIEVER = None


def get_semantic_retriever() -> SemanticRetriever:
    global _RETRIEVER
    with _RETRIEVER_LOCK:
        if _RETRIEVER is None:
            _RETRIEVER = LocalSemanticRetriever()
        return _RETRIEVER


def set_semantic_retriever(retriever) -> None:
    """Installe/remplace le retriever (tests, impl. externe)."""
    global _RETRIEVER
    with _RETRIEVER_LOCK:
        _RETRIEVER = retriever
        # le cache de candidats d'une nouvelle impl n'est plus valide
        try:
            clear = getattr(retriever, "clear_cache", None)
            if callable(clear):
                clear()
        except Exception:
            pass


__all__ = [
    "SEMANTIC_STATUS",
    "SEMANTIC_MIN_SCORE",
    "SemanticMatch",
    "SemanticSearchOutcome",
    "SemanticRetriever",
    "LocalSemanticRetriever",
    "get_semantic_retriever",
    "set_semantic_retriever",
    "RETRIEVER",
]
