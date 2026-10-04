"""Tests offline — tool propose_knowledge ( soumission a approbation admin ).

Le tool ecrit via le store knowledge ; on monkeypatche le store pour
tester le CONTRAT du tool ( JSON, statuts, garde-fous ) sans base.
"""

from __future__ import annotations

import json

from app.tools.knowledge import propose_knowledge


def _patch(monkeypatch, status, created=None, boom=False):
    import app.services.knowledge.store as store

    monkeypatch.setattr(store, "get_subject_status", lambda sid: status)

    def _create(**kw):
        if boom:
            raise RuntimeError("DB down")
        created.append(kw)
        return {"id": 42, "subject_id": kw["subject_id"], "title": kw["title"], "status": "pending"}

    monkeypatch.setattr(store, "create_proposal", _create)


def test_proposal_created(monkeypatch):
    calls = []
    _patch(monkeypatch, "validated", calls)
    out = json.loads(propose_knowledge.invoke({
        "subject": "python",
        "title": "Closures",
        "content": "Une closure retient son environnement lexical.",
        "reason": "Complement manquant",
    }))
    assert out["status"] == "proposed"
    assert out["proposal_id"] == 42
    assert calls and calls[0]["reason"] == "Complement manquant"


def test_unknown_subject_rejected(monkeypatch):
    calls = []
    _patch(monkeypatch, None, calls)
    out = json.loads(propose_knowledge.invoke({
        "subject": "inexistante", "title": "T", "content": "C",
    }))
    assert out["status"] == "rejected"
    assert calls == []


def test_missing_fields_rejected(monkeypatch):
    calls = []
    _patch(monkeypatch, "validated", calls)
    out = json.loads(propose_knowledge.invoke({
        "subject": "python", "title": "T", "content": "   ",
    }))
    assert out["status"] == "rejected"
    assert calls == []


def test_store_error_is_contained(monkeypatch):
    _patch(monkeypatch, "validated", [], boom=True)
    out = json.loads(propose_knowledge.invoke({
        "subject": "python", "title": "T", "content": "C",
    }))
    assert out["status"] == "error"
