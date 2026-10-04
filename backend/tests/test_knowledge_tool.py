"""Tests — tool search_knowledge ( recherche corpus exposée au LLM ).

Le tool délègue à knowledge_retriever.search_knowledge ; on monkeypatche
ce dernier pour tester le CONTRAT du tool ( JSON, statuts, author )
sans base ni provider d'embedding.
"""

from __future__ import annotations

import json

from app.tools.knowledge import search_knowledge


def test_tool_query_vide_unavailable():
    out = json.loads(
        search_knowledge.invoke({"subject": "python", "query": "   "})
    )
    assert out["status"] == "unavailable"
    assert out["results"] == []


def test_tool_subject_vide_unavailable():
    out = json.loads(
        search_knowledge.invoke({"subject": "", "query": "fonctions"})
    )
    assert out["status"] == "unavailable"


def test_tool_wraps_retriever(monkeypatch):
    import app.services.context.knowledge_retriever as kr

    def fake_search(subject_id, topic=None, query="", limit=3, **kw):
        return {
            "status": "found",
            "query": query,
            "results": [
                {
                    "title": "Fonctions",
                    "source": "python/fonctions",
                    "content": "Une fonction regroupe des instructions.",
                    "relevance": 0.87,
                    "metadata": {"author": "Pr. X"},
                }
            ],
            "items": [],
            "searched_sources": 1,
        }

    monkeypatch.setattr(kr, "search_knowledge", fake_search)
    out = json.loads(
        search_knowledge.invoke({"subject": "python", "query": "fonctions"})
    )
    assert out["status"] == "found"
    assert out["subject"] == "python"
    assert out["results"][0]["author"] == "Pr. X"
    assert out["results"][0]["relevance"] == 0.87


def test_tool_never_raises(monkeypatch):
    import app.services.context.knowledge_retriever as kr

    def boom(*a, **k):
        raise RuntimeError("DB down")

    monkeypatch.setattr(kr, "search_knowledge", boom)
    out = json.loads(
        search_knowledge.invoke({"subject": "python", "query": "x"})
    )
    assert out["status"] == "error"
