# Reranking du corpus — second étage de tri APRES la recherche hybride.
#
# La recherche hybride ( store.search_hybrid ) genere un POOL de
# candidates ( cosine HNSW + tsvector GIN ). Le reranker les RE-CLASSE
# avec des signaux lexicaux fins que le vecteur ne capture pas :
#   - coverage : part des mots de la requete presents dans le passage ;
#   - title    : part des mots de la requete presents dans le titre ;
#   - phrase   : la requete ( normalisee ) apparait-elle telle quelle ?
#
# L implementation est INTERCHANGEABLE ( Protocol + get/set ) : un
# reranker LLM ( cross-encoder ) peut etre branche sans toucher au
# retriever ni au tool. Defaut = heuristique deterministe LOCALE.
#
# CYCLE D IMPORT : normalize_query vit dans app.services.context, dont
# le __init__ importe le builder, qui importe knowledge_retriever, qui
# importe CE module. L import de query_norm est donc fait a l appel
# ( _norm ), jamais au niveau module.
from __future__ import annotations

import threading
from typing import Protocol

# Pondérations du reranker heuristique ( centralisees, testables ).
RERANK_BASE_WEIGHT = 0.50      # score hybride d origine ( recall )
RERANK_COVERAGE_WEIGHT = 0.25  # couverture des mots de la requete
RERANK_TITLE_WEIGHT = 0.15     # mots de la requete dans le TITRE
RERANK_PHRASE_WEIGHT = 0.10    # requete presente litteralement


def _norm(text: str) -> str:
    """Normalise un texte ( accents, casse, ponctuation ).

    Import paresseux : charger app.services.context au niveau module
    creerait un cycle d import. Voir l en-tete du fichier.
    """
    from app.services.context.query_norm import normalize_query

    return normalize_query(text or "")


def _tokens(text: str) -> set[str]:
    """Tokens normalises ( accents, casse, ponctuation ) d un texte."""
    return {t for t in _norm(text).split() if t}


class Reranker(Protocol):
    """Interface stable du reranker ( interchangeable )."""

    name: str

    def rerank(
        self, query: str, candidates: list[dict], top_k: int = 3
    ) -> list[dict]:
        ...


class LocalHeuristicReranker:
    """Reranker local deterministe ( signaux lexicaux + score )."""

    name = "local-heuristic-rerank-v1"

    def rerank(
        self, query: str, candidates: list[dict], top_k: int = 3
    ) -> list[dict]:
        """Re-classe les candidates par score composite et retourne top_k.

        Chaque candidat doit porter au moins title, content, relevance.
        La pertinence finale REMPLACE relevance ; les signaux sont
        conserves dans la cle rerank. Jamais d erreur : liste vide
        renvoie liste vide ; requete vide renvoie les candidats inchanges.
        """
        if not candidates:
            return []
        q = (query or "").strip()
        q_tokens = _tokens(q)
        if not q_tokens:
            return candidates[:top_k]
        q_norm = _norm(q)

        scored: list[tuple[float, dict]] = []
        for cand in candidates:
            base = float(cand.get("relevance", 0.0) or 0.0)
            content = cand.get("content", "") or ""
            doc_tokens = _tokens(content)
            title_tokens = _tokens(cand.get("title", ""))
            n = len(q_tokens) or 1
            coverage = len(q_tokens & doc_tokens) / n
            title_hit = len(q_tokens & title_tokens) / n
            phrase = 1.0 if q_norm and q_norm in _norm(content) else 0.0
            score = (
                RERANK_BASE_WEIGHT * base
                + RERANK_COVERAGE_WEIGHT * coverage
                + RERANK_TITLE_WEIGHT * title_hit
                + RERANK_PHRASE_WEIGHT * phrase
            )
            out = dict(cand)
            out["relevance"] = round(score, 4)
            out["rerank"] = {
                "base": round(base, 4),
                "coverage": round(coverage, 4),
                "title": round(title_hit, 4),
                "phrase": phrase,
            }
            scored.append((score, out))

        scored.sort(key=lambda t: t[0], reverse=True)
        return [c for _s, c in scored[: max(1, int(top_k))]]


# ------------------------------------------------------------------
# Reranker actif — configurable ( Protocol interchangeable )
# ------------------------------------------------------------------
_RERANKER_LOCK = threading.RLock()
_RERANKER: Reranker = LocalHeuristicReranker()


def get_reranker() -> Reranker:
    """Reranker actif ( local heuristique par defaut )."""
    return _RERANKER


def set_reranker(reranker: Reranker) -> None:
    """Installe/remplace le reranker ( tests, impl. LLM )."""
    global _RERANKER
    with _RERANKER_LOCK:
        _RERANKER = reranker


def rerank(
    query: str, candidates: list[dict], top_k: int = 3
) -> list[dict]:
    """Applique le reranker ACTIF — facade stable pour les appelants."""
    return get_reranker().rerank(query, candidates, top_k=top_k)


__all__ = [
    "RERANK_BASE_WEIGHT",
    "RERANK_COVERAGE_WEIGHT",
    "RERANK_TITLE_WEIGHT",
    "RERANK_PHRASE_WEIGHT",
    "Reranker",
    "LocalHeuristicReranker",
    "get_reranker",
    "set_reranker",
    "rerank",
]