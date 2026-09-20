# DocumentRetriever V10 — façade d'accès aux documents utilisateur.
#
# Sépare le STOCKAGE (RagStore) de l'USAGE métier :
#   - inject_documents_context() : formatage « citations » prêt
#     pour le SystemPrompt (create_context V6.5) ;
#   - search_documents()          : recherche contrôlée (statut
#     found/insufficient/unavailable/error) pour le tool agent.
#
# La récupération NE LÈVE JAMAIS : tout échec → réponse contrôlée
# ou chaîne vide (fail-safe mission §15 : aucun document ne doit
# casser le pipeline du chat).
from __future__ import annotations

import logging

from app.rag.schemas import DocumentSearchResponse, DocumentSearchResult
from app.rag.vector_store import RagStore, get_rag_store

logger = logging.getLogger("rag")

# Seuil par défaut d'une recherche « utile » (tool/API). Sous ce
# seuil → statut insufficient (contrôlé, cohérent avec le reste).
DEFAULT_SCORE_THRESHOLD = 0.05

# Fermer la requête : MAX 4 chunks injectés dans le contexte
# (budget tokens du SystemPrompt).
MAX_CONTEXT_CHUNKS = 4


class DocumentRetriever:
    """Façade de retrieval documents utilisateur (stateless)."""

    def __init__(self, store: RagStore | None = None):
        self._store = store or get_rag_store()

    # ------------------------------------------------------------------
    # API publique (tool agent )
    # ------------------------------------------------------------------
    def search_documents(
        self,
        *,
        user_id: str,
        query: str,
        top_k: int = 5,
        score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    ) -> DocumentSearchResponse:
        """Recherche contrôlée (tool `search_documents`).

        Jamais d'exception : un provider KO → statut error.
        """
        if not user_id or not query or not query.strip():
            return DocumentSearchResponse(
                status="unavailable", query=query or ""
            )
        try:
            return self._store.search(
                user_id=user_id,
                query=query,
                top_k=max(1, min(int(top_k), 20)),
                score_threshold=score_threshold,
            )
        except Exception as exc:  # pragma: no cover — défensif
            logger.error("search_documents échec: %s", exc)
            return DocumentSearchResponse(
                status="error", query=query, error=str(exc)
            )

    # ------------------------------------------------------------------
    # Formatage contexte (SystemPrompt)
    # ------------------------------------------------------------------
    def inject_documents_context(
        self,
        *,
        user_id: str,
        query: str,
        max_chunks: int = MAX_CONTEXT_CHUNKS,
    ) -> str:
        """Bloc « Documents personnels » pour le SystemPrompt.

        Retourne "" si rien d'utile (fail-safe). Format :
            ## Documents utilisateur (extraits pertinents)
            [cours-python.md] <extrait>
        """
        if not user_id or not query or not query.strip():
            return ""
        resp = self.search_documents(
            user_id=user_id,
            query=query,
            top_k=max_chunks,
        )
        if resp.status != "found" or not resp.results:
            return ""
        return self._format_results(resp.results)

    @staticmethod
    def _format_results(results: list[DocumentSearchResult]) -> str:
        lines = ["## Documents utilisateur (extraits pertinents)"]
        for r in results:
            src = r.filename or r.doc_id
            snippet = r.content.strip().replace("\n", " ")[:300]
            if len(snippet) == 300:
                snippet += "…"
            lines.append(f"[{src}] {snippet}")
        return "\n".join(lines)


__all__ = [
    "DEFAULT_SCORE_THRESHOLD",
    "DocumentRetriever",
    "MAX_CONTEXT_CHUNKS",
]