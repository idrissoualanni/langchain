# RAG package V10 — User Document Knowledge.
#
# Périmètre V10 (mission) :
#   - réutilise le provider embeddings existant (app.context.semantic.provider)
#   - stockage vecteurs SQLite (aucun service externe) — chunk + embedding
#   - retrieval hybride lexical (FTS5) + sémantique (cosine)
#   - expose UN contrat public : rag_store / search_documents /
#     index_document / delete_document / list_documents