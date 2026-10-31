"""Reproduction — couche faits mémoire (services/memory/memory.py).

Bugs reproduits (tous en production avant correctif) :
  - search_facts appelait HybridRetriever.retrieve(user_id=…) → TypeError,
    la route /memory/search répondait 500 ;
  - list/search renvoyaient {content, metadata, type, score} alors que
    l'API construit MemoryFactOut(id, category, source, confidence, …) ;
  - delete_fact ne supprimait rien mais répondait {"deleted": id} ;
  - update_fact ignorait category/confidence (TypeError) et dupliquait ;
  - un patch de profil partiel effaçait les autres champs ;
  - un vecteur de mauvaise dimension était complété de zéros en silence.
"""
from __future__ import annotations

import uuid

import pytest

from app.schemas.memory import MemoryFactOut
from app.services.memory import cognitive_store as cs_module
from app.services.memory import memory


class FakeCognitiveStore:
    """Store en mémoire — même interface que CognitiveStore."""

    def __init__(self):
        self.rows: dict[str, dict] = {}

    def _new(self, user_id, content, memory_type, metadata):
        mid = str(uuid.uuid4())
        self.rows[mid] = {
            "id": mid, "user_id": user_id, "content": content,
            "metadata": dict(metadata or {}), "type": memory_type,
            "created_at": "2026-10-31T00:00:00+00:00",
            "updated_at": "2026-10-31T00:00:00+00:00",
        }
        return mid

    def save_memory(self, user_id, content, memory_type="fact", metadata=None):
        return self._new(user_id, content, memory_type, metadata)

    def get_memory(self, user_id, memory_id):
        row = self.rows.get(memory_id)
        return dict(row) if row and row["user_id"] == user_id else None

    def list_memories(self, user_id, memory_type=None, limit=100):
        return [
            dict(r) for r in self.rows.values()
            if r["user_id"] == user_id
            and r["metadata"].get("type") != "profile"
            and (memory_type is None or r["type"] == memory_type)
        ][:limit]

    def retrieve_memories(self, user_id, query, limit=5, min_score=0.5):
        hits = [r for r in self.list_memories(user_id) if query.lower() in r["content"].lower()]
        return [{**r, "score": 0.9} for r in hits][:limit]

    def update_memory(self, user_id, memory_id, content=None, memory_type=None, metadata_patch=None):
        row = self.get_memory(user_id, memory_id)
        if row is None:
            return None
        stored = self.rows[memory_id]
        if content is not None:
            stored["content"] = content
        if memory_type is not None:
            stored["type"] = memory_type
        stored["metadata"].update(metadata_patch or {})
        return dict(stored)

    def delete_memory(self, user_id, memory_id):
        if self.get_memory(user_id, memory_id) is None:
            return False
        del self.rows[memory_id]
        return True

    def latest_profile(self, user_id):
        profiles = [
            r["metadata"] for r in self.rows.values()
            if r["user_id"] == user_id and r["metadata"].get("type") == "profile"
        ]
        return profiles[-1] if profiles else None


@pytest.fixture
def store(monkeypatch):
    fake = FakeCognitiveStore()
    monkeypatch.setattr(cs_module, "cognitive_store", fake)
    return fake


USER = "user-a"


def test_save_et_list_respectent_le_contrat_api(store):
    memory.save_fact(USER, "interest", "Aime la robotique", confidence=0.8)

    facts = memory.list_facts(USER)

    assert len(facts) == 1
    fact = MemoryFactOut(**facts[0])  # ne lève plus de ValidationError
    assert fact.category == "interest"
    assert fact.confidence == 0.8


def test_search_cherche_dans_les_faits_de_l_utilisateur(store):
    memory.save_fact(USER, "interest", "Aime la robotique")
    memory.save_fact("user-b", "interest", "Aime la robotique aussi")

    results = memory.search_facts(USER, "robotique")

    assert [MemoryFactOut(**r).content for r in results] == ["Aime la robotique"]


def test_delete_supprime_vraiment(store):
    fact = memory.save_fact(USER, "interest", "À effacer")

    assert memory.delete_fact(USER, fact["id"]) == {"deleted": fact["id"]}
    assert memory.list_facts(USER) == []


def test_delete_d_un_fait_inexistant_ou_d_autrui_leve(store):
    fact = memory.save_fact("user-b", "interest", "Pas à moi")

    with pytest.raises(ValueError):
        memory.delete_fact(USER, fact["id"])
    assert len(store.rows) == 1


def test_update_modifie_en_place_sans_dupliquer(store):
    fact = memory.save_fact(USER, "interest", "Python")

    updated = memory.update_fact(
        USER, fact["id"], content="Python avancé", category="preference", confidence=0.5
    )

    assert len(store.rows) == 1
    out = MemoryFactOut(**updated)
    assert (out.content, out.category, out.confidence) == ("Python avancé", "preference", 0.5)


def test_update_d_un_fait_inexistant_leve(store):
    with pytest.raises(ValueError):
        memory.update_fact(USER, str(uuid.uuid4()), content="x")


def test_patch_de_profil_partiel_conserve_les_autres_champs(store):
    memory.write_profile(USER, {"name": "Ada", "description": "Étudiante"})
    memory.write_profile(USER, {"name": "Ada L."})

    assert memory.read_profile(USER) == {"name": "Ada L.", "description": "Étudiante"}
    assert memory.list_facts(USER) == []  # le profil n'est pas un fait


def test_overview_classe_par_categorie(store):
    memory.save_fact(USER, "interest", "Robotique")

    overview = memory.memory_overview_for_api(USER)

    assert overview["total_facts"] == 1
    assert overview["facts_by_category"]["interest"][0]["content"] == "Robotique"


class _Conn:
    def __init__(self, column_dim):
        self.column_dim = column_dim

    def execute(self, *_a, **_k):
        dim = self.column_dim

        class _R:
            def first(self_inner):
                return (dim,)

        return _R()


def test_dimension_incompatible_est_refusee_sans_padding(monkeypatch):
    from app.core.exceptions import AppMemoryError

    class Provider:
        _model = "m"

        def embed_text(self, _):
            return [0.1] * 8

    monkeypatch.setattr(cs_module, "get_embedding_provider", lambda: Provider())
    store = cs_module.CognitiveStore()

    with pytest.raises(AppMemoryError):
        store._embed(_Conn(column_dim=16), "texte")

    literal, model = cs_module.CognitiveStore()._embed(_Conn(column_dim=8), "texte")
    assert literal.count(",") == 7 and model == "Provider:m"
