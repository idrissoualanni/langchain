"""Tests offline — reranking du corpus ( deuxieme etage de tri ).

Verifie que le reranker LOCAL re-classe le pool issu de la recherche
hybride : un candidat lexicalement pertinent doit remonter devant un
candidat seulement-semantique. Aucune base, aucun provider.
"""

from __future__ import annotations

from app.services.knowledge.rerank import (
    LocalHeuristicReranker,
    get_reranker,
    rerank,
    set_reranker,
)


def _cand(title: str, content: str, relevance: float) -> dict:
    return {"title": title, "content": content, "relevance": relevance}


def test_empty_candidates():
    assert rerank("fonction", []) == []


def test_empty_query_returns_as_is():
    cands = [_cand("A", "contenu", 0.5), _cand("B", "autre", 0.4)]
    assert rerank("", cands, top_k=1) == cands[:1]


def test_lexical_coverage_beats_pure_semantic():
    # cand_sem : score hybride eleve mais AUCUNE couverture lexicale ;
    # cand_lex : score hybride plus faible mais requete entierement couverte.
    cand_sem = _cand("Geometrie", "Le theoreme de Pythagore.", 0.90)
    cand_lex = _cand(
        "Fonction recursive",
        "Une fonction recursive s appelle elle meme dans son corps.",
        0.50,
    )
    out = rerank("fonction recursive", [cand_sem, cand_lex], top_k=2)
    assert out[0]["title"] == "Fonction recursive"
    assert out[0]["relevance"] > out[1]["relevance"]


def test_accents_are_folded():
    cand = _cand("Recursivite", "Une fonction recursive s appelle elle meme.", 0.4)
    out = rerank("fonction r\u00e9cursive", [cand], top_k=1)
    assert out[0]["rerank"]["coverage"] == 1.0


def test_signals_exposed_and_top_k_respected():
    cands = [_cand("A", "a propos de foo", 0.8), _cand("B", "bar baz", 0.7)]
    out = rerank("foo", cands, top_k=1)
    assert len(out) == 1
    assert set(out[0]["rerank"]) == {"base", "coverage", "title", "phrase"}


def test_custom_reranker_pluggable():
    class Reverse:
        name = "reverse"

        def rerank(self, query, candidates, top_k=3):
            return list(reversed(candidates))[:top_k]

    previous = get_reranker()
    try:
        set_reranker(Reverse())
        cands = [_cand("A", "x", 0.9), _cand("B", "y", 0.1)]
        assert rerank("q", cands, top_k=2)[0]["title"] == "B"
    finally:
        set_reranker(previous)
    assert isinstance(get_reranker(), LocalHeuristicReranker)
