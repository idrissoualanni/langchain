import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from app.services.memory.cognitive_store import cognitive_store
from app.services.memory.hybrid_retriever import HybridRetriever

# --- Mocks for Embedding Provider ---

class MockEmbeddingProvider:
    """Embeddings creux : un bucket sémantique par famille de mots-clés.

    Le cosinus entre deux vecteurs constants est TOUJOURS 1.0 (les
    constantes s'annulent) : avec [0.1]*1536 pour tous les fruits,
    le filtre min_score ne retiendrait rien et tous les faits
    matcheraient. Chaque famille occupe donc un bucket distinct —
    cosinus 1.0 si même bucket, 0.0 sinon, comme le pgvector.
    """

    BUCKETS = (
        (("apple", "fruit", "pommes"), 10),
        (("python", "coding"), 20),
        (("paris", "city"), 30),
    )

    def embed_text(self, text: str) -> list[float]:
        vec = [0.0] * 1536
        t = text.lower()
        for keywords, idx in self.BUCKETS:
            if any(k in t for k in keywords):
                vec[idx] = 1.0
                break
        else:
            vec[40] = 1.0
        return vec

@pytest.fixture(autouse=True)
def mock_embedding_provider():
    # Patch sur le namespace du CONSOMMATEUR : cognitive_store fait
    # `from ...provider import get_embedding_provider` (capture par
    # valeur) — patcher le module source ne l'atteindrait pas.
    #
    # Le provider retient le dernier texte embarqué : c'est ainsi que
    # les mocks de requête SQL retrouvent la query (retrieve_memories
    # appelle embed_text(query) AVANT d'exécuter le SELECT).
    state = {"last_query": None}
    with patch("app.services.memory.cognitive_store.get_embedding_provider") as mock:
        mock_provider = MagicMock()

        def _embed(text):
            state["last_query"] = text
            return MockEmbeddingProvider().embed_text(text)

        mock_provider.embed_text.side_effect = _embed
        mock_provider.name = "mock-provider"
        mock.return_value = mock_provider
        mock.last_query = state
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

    @staticmethod
    def _select_rows(user_data, query, min_score=0.5):
        """Mock du SELECT pgvector : score cosinus via le provider mocké.

        Filtre les faits par pertinence réelle (embedding de la requête
        vs contenu) — simule `1 - (embedding <=> :embedding) >= min_score`.
        """
        from app.services.memory.cognitive_store import (
            get_embedding_provider,
        )
        from app.services.context.semantic.provider import (
            cosine_similarity,
        )

        provider = get_embedding_provider()
        q_vec = provider.embed_text(query)
        rows = []
        for d in user_data:
            score = cosine_similarity(q_vec, provider.embed_text(d["content"]))
            if score >= min_score:
                rows.append((d["id"], d["content"], "{}", "fact",
                             "2026-10-31", "2026-10-31", score))
        return rows

    def test_sovereignty(self, mock_embedding_provider):
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
                if "pg_attribute" in query_str:
                    result = MagicMock()
                    result.first.return_value = None  # dimension inconnue
                    return result
                if "SELECT id, content" in query_str:
                    uid = params["user_id"]
                    # La query est le dernier texte embarqué AVANT le SELECT
                    # (retrieve_memories appelle embed_text(query) juste
                    # avant le SQL ; _select_rows embarque les contenus
                    # ensuite et écraserait last_query).
                    query = mock_embedding_provider.last_query["last_query"]
                    rows = self._select_rows(
                        storage.get(uid, []),
                        query,
                        params["min_score"],
                    )
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

    def test_semantic_hnsw_retrieval(self, mock_embedding_provider):
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
                if "pg_attribute" in query_str:
                    result = MagicMock()
                    result.first.return_value = None  # dimension inconnue
                    return result
                if "SELECT id, content" in query_str:
                    uid = params["user_id"]
                    rows = self._select_rows(
                        storage.get(uid, []),
                        mock_embedding_provider.last_query["last_query"],
                        params["min_score"],
                    )
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
                # _apply_mmr fait _engine().connect().execute()...
                # Structure à DEUX niveaux : engine → connect() → execute().
                # Vecteurs creux normalisés : t1/t2/t3 = bucket Python,
                # t4/t5 = bucket froid. Produit scalaire = 1.0 si même
                # bucket, 0.0 sinon — comme le cosinus pgvector. (Des
                # vecteurs constants non normalisés donnaient un produit
                # scalaire de 61.44 qui cassait le calcul MMR.)
                def vec(bucket):
                    v = [0.0] * 1536
                    v[bucket] = 1.0
                    return v
                VECS = {"t1": vec(20), "t2": vec(20), "t3": vec(20),
                        "t4": vec(30), "t5": vec(30)}

                class _Result:
                    def __iter__(self):
                        return [(k, v) for k, v in VECS.items()]
                    def fetchall(self):
                        return [(k, v) for k, v in VECS.items()]
                    def scalar(self):
                        return 1

                class _InnerConn:
                    def execute(self, query, params=None):
                        return _Result()
                    def __enter__(self):
                        return self
                    def __exit__(self, *args):
                        pass

                class _EngineMock:
                    def connect(self):
                        return _InnerConn()

                mock_engine_store.side_effect = lambda *a, **kw: _EngineMock()
                results = retriever.retrieve("subj", "Python et météo", limit=2)
                contents = [r["content"] for r in results]
                assert any("Python" in c for c in contents)
                assert any("froid" in c or "hiver" in c for c in contents)
                assert len(results) == 2

    def test_neon_persistence(self, mock_embedding_provider):
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
                if "pg_attribute" in query_str:
                    result = MagicMock()
                    result.first.return_value = None  # dimension inconnue
                    return result
                if "SELECT id, content" in query_str:
                    uid = params["user_id"]
                    rows = self._select_rows(
                        storage.get(uid, []),
                        mock_embedding_provider.last_query["last_query"],
                        params["min_score"],
                    )
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
