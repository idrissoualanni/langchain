# Semantic layer V7.1 — compréhension sémantique interchangeable.
#
# FRONTIÈRE (mission §6/§21) : le reste du projet ne dépend QUE de
#   - SemanticRetriever.search(query, candidates, top_k) → SemanticSearchOutcome
#   - EmbeddingProvider (interchangeable, jamais codé en dur)
# Le Learning Engine / BuiltContext ne savent RIEN de l'algorithme
# d'embedding (mission §21).
from app.services.context.semantic.candidates import (
    TopicCandidate,
    build_topic_candidates,
)
from app.services.context.semantic.provider import (
    EmbeddingProvider,
    LocalHashEmbeddingProvider,
    cosine_similarity,
    get_embedding_provider,
    set_embedding_provider,
)
from app.services.context.semantic.retriever import (
    RETRIEVER,
    SemanticRetriever,
    LocalSemanticRetriever,
    get_semantic_retriever,
    set_semantic_retriever,
)

__all__ = [
    "TopicCandidate",
    "build_topic_candidates",
    "EmbeddingProvider",
    "LocalHashEmbeddingProvider",
    "cosine_similarity",
    "get_embedding_provider",
    "set_embedding_provider",
    "SemanticRetriever",
    "LocalSemanticRetriever",
    "get_semantic_retriever",
    "set_semantic_retriever",
    "RETRIEVER",
]
