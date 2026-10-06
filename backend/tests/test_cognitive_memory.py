import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from app.services.memory.cognitive_store import cognitive_store
from app.services.memory.hybrid_retriever import HybridRetriever

# --- Mocks for Embedding Provider ---

class MockEmbeddingProvider:
    def embed_text(self, text: str) -> list[float]:
        if "apple" in text.lower() or "fruit" in text.lower() or "pommes" in text.lower():
            return [0.1] * 1536
        if "python" in text.lower() or "coding" in text.lower():
            return [0.2] * 1536
        if "paris" in text.lower() or "city" in text.lower():
            return [0.3] * 1536
        return [0.0] * 1536

@pytest.fixture(autouse=True)
def mock_embedding_provider():
    with patch("app.services.context.semantic.provider.get_embedding_provider") as mock:
        mock_provider = MagicMock()
        mock_provider.embed_text.side_effect = MockEmbeddingProvider().embed_text
        mock_provider.name = "mock-provider"
        mock.return_value = mock_provider
        yield mock

@pytest.fixture(autouse=True)
def mock_all_embedding_calls():
    with patch("app.services.context.semantic.provider.CloudflareWorkersAIEmbeddingProvider.embed_text") as mock_cf, \
         patch("app.services.context.semantic.provider.OllamaEmbeddingProvider.embed_text") as mock_ol:
        mock_cf.side_effect = MockEmbeddingProvider().embed_text
        mock_ol.side_effect = MockEmbeddingProvider().embed_text
        yield

# --- Test Data ---

USER_A = "user_alpha"
USER_B = "user_beta"

FACTS_A = [
    {"content": "L'utilisateur adore les pommes et les fruits rouges.", "type": "preference"},
    {"content": "Il maîtrise le langage Python et le développement backend.", "type": "fact"},
    {"content": "Il habite à Paris, la capitale de la France.", "type": "fact"},
]

FACTS_B = [
    {"content": "L'utilisateur déteste les pommes.", "type": "preference"},
    {"content": "Il ne connaît pas la programmation.", "type": "fact"},
]

# --- Tests ---

class TestCognitiveMemoryIntegration:

    def test_sovereignty(self):
        """Vérifier qu'un utilisateur ne peut pas lire/modifier la mémoire d'un autre utilisateur."""
        with patch("app.services.memory.cognitive_store.CognitiveStore._get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine

            storage = {}
            def mock_execute(query, params=None):
                query_str = str(query)
                if "INSERT INTO user_cognitive_memories" in query_str:
                    uid = params["user_id"]
                    if uid not in storage: storage[uid] = []
                    mid = len(storage[uid]) + 1
                    storage[uid].append({"content": params["content"], "id": mid})
                    result = MagicMock()
                    result.scalar.return_value = mid
                    return result
                if "SELECT content" in query_str:
                    uid = params["user_id"]
                    user_data = storage.get(uid, [])
                    rows = [(d["content"], "{}", "fact", 0.9) for d in user_data]
                    result = MagicMock()
                    result.__iter__.return_value = rows
                    return result

            mock_engine.begin.return_value.__enter__.return_value.execute.side_effect = mock_execute
            mock_engine.connect.return_value.__enter__.return_value.execute.side_effect = mock_execute

            for f in FACTS_A:
                cognitive_store.save_memory(USER_A, f["content"], f["type"])
            for f in FACTS_B:
                cognitive_store.save_memory(USER_B, f["content"], f["type"])

            results_a = cognitive_store.retrieve_memories(USER_A, "pommes")
            for res in results_a:
                assert "pommes et les fruits rouges" in res["content"]
                assert "déteste les pommes" not in res["content"]

            results_b = cognitive_store.retrieve_memories(USER_B, "pommes")
            for res in results_b:
                assert "déteste les pommes" in res["content"]
                assert "pommes et les fruits rouges" not in res["content"]

    def test_semantic_hnsw_retrieval(self):
        """Vérifier que la récupération fonctionne par le SENS."""
        with patch("app.services.memory.cognitive_store.CognitiveStore._get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine

            storage = {}
            def mock_execute(query, params=None):
                query_str = str(query)
                if "INSERT INTO user_cognitive_memories" in query_str:
                    uid = params["user_id"]
                    if uid not in storage: storage[uid] = []
                    mid = len(storage[uid]) + 1
                    storage[uid].append({"content": params["content"], "id": mid})
                    result = MagicMock()
                    result.scalar.return_value = mid
                    return result
                if "SELECT content" in query_str:
                    uid = params["user_id"]
                    user_data = storage.get(uid, [])
                    rows = [(d["content"], "{}", "fact", 0.9) for d in user_data]
                    result = MagicMock()
                    result.__iter__.return_value = rows
                    return result

            mock_engine.begin.return_value.__enter__.return_value.execute.side_effect = mock_execute
            mock_engine.connect.return_value.__enter__.return_value.execute.side_effect = mock_execute

            cognitive_store.save_memory(USER_A, "L'utilisateur adore les pommes.", "preference")
            results = cognitive_store.retrieve_memories(USER_A, "Quels fruits aime-t-il ?")

            assert len(results) > 0
            assert "pommes" in results[0]["content"]

    def test_mmr_diversity(self):
        """Vérifier que le retrieval ne renvoie pas de doublons sémantiques via MMR."""
        facts = [
            "J'adore le langage Python.",
            "Je suis fan de Python.",
            "Le Python est mon langage préféré.",
            "Je déteste le froid.",
            "Je n'aime pas l'hiver.",
        ]
        with patch("app.services.memory.cognitive_store.CognitiveStore._get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine
            mock_engine.begin.return_value.__enter__.return_value.execute.return_value.scalar.return_value = "123"

            for f in facts:
                cognitive_store.save_memory(USER_A, f, "fact")

        retriever = HybridRetriever(lambda_mmr=0.3)
        with patch("app.services.knowledge.store.search_hybrid") as mock_search:
            mock_search.return_value = [
                {"topic": "t1", "title": "f1", "content": facts[0], "source": "s", "relevance": 0.9},
                {"topic": "t2", "title": "f2", "content": facts[1], "source": "s", "relevance": 0.88},
                {"topic": "t3", "title": "f3", "content": facts[2], "source": "s", "relevance": 0.85},
                {"topic": "t4", "title": "f4", "content": facts[3], "source": "s", "relevance": 0.7},
                {"topic": "t5", "title": "f5", "content": facts[4], "source": "s", "relevance": 0.65},
            ]
            with patch("app.services.knowledge.store._engine") as mock_engine_store:
                def side_effect(*args, **kwargs):
                    class Conn:
                        def execute(self, query, params=None):
                            class Result:
                                def __iter__(self):
                                    # Return dummy vectors: t1,t2,t3 are same, t4,t5 are same
                                    # This is a simplified mock
                                    return [("t1", [0.2]*1536), ("t2", [0.2]*1536), ("t3", [0.2]*1536), ("t4", [0.5]*1536), ("t5", [0.5]*1536)]
                                def scalar(self): return 1
                            return Result()
                        def __enter__(self): return self
                        def __exit__(self, *args): pass
                    return Conn()
                mock_engine_store.return_value = side_effect
                results = retriever.retrieve("subj", "Python et météo", limit=2)
                contents = [r["content"] for r in results]
                assert any("Python" in c for c in contents)
                assert any("froid" in c or "hiver" in c for c in contents)
                assert len(results) == 2

    def test_neon_persistence(self):
        """Vérifier que les embeddings sont correctement stockés et récupérés via CognitiveStore."""
        with patch("app.services.memory.cognitive_store.CognitiveStore._get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine

            storage = {}
            def mock_execute(query, params=None):
                query_str = str(query)
                if "INSERT INTO user_cognitive_memories" in query_str:
                    uid = params["user_id"]
                    if uid not in storage: storage[uid] = []
                    mid = len(storage[uid]) + 1
                    storage[uid].append({"content": params["content"], "id": mid})
                    result = MagicMock()
                    result.scalar.return_value = mid
                    return result
                if "SELECT content" in query_str:
                    uid = params["user_id"]
                    user_data = storage.get(uid, [])
                    rows = [(d["content"], "{}", "fact", 0.9) for d in user_data]
                    result = MagicMock()
                    result.__iter__.return_value = rows
                    return result

            mock_engine.begin.return_value.__enter__.return_value.execute.side_effect = mock_execute
            mock_engine.connect.return_value.__enter__.return_value.execute.side_effect = mock_execute

            content = "Ceci est un fait persistant unique."
            mem_id = cognitive_store.save_memory(USER_A, content, "fact")
            assert mem_id != "fallback_id"
            results = cognitive_store.retrieve_memories(USER_A, content)
            assert len(results) > 0
            assert results[0]["content"] == content
