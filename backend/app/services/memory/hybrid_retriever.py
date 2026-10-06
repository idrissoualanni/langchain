# Hybrid Retriever — Moteur de recherche "Sens Réel"
#
# Ce module implémente une stratégie de récupération hybride combinant :
# 1. Recherche Vectorielle (Sémantique) : Capture l'intention et le concept.
# 2. Recherche Lexicale (BM25 / FTS) : Capture les termes précis et les mots-clés.
#
# L'algorithme MMR (Maximum Marginal Relevance) est utilisé pour diversifier
# les résultats, évitant la redondance tout en maintenant la pertinence.

from __future__ import annotations

import numpy as np
from typing import Protocol, TypedDict
from app.services.knowledge import store
from app.logging.events import log_event

class RetrievalResult(TypedDict):
    topic: str
    title: str
    content: str
    source: str
    relevance: float
    method: str # 'semantic', 'lexical', or 'hybrid'

class Retriever(Protocol):
    def retrieve(self, subject_id: str, query: str, limit: int = 3) -> list[RetrievalResult]:
        ...

class HybridRetriever:
    """
    Implémentation du moteur "Sens Réel".
    Combine pgvector et PostgreSQL Full-Text Search (FTS).
    """

    name = "sens-reel-hybrid-v1"

    def __init__(self, semantic_weight: float = 0.6, lambda_mmr: float = 0.5):
        """
        :param semantic_weight: Poids accordé à la recherche vectorielle (0.0 to 1.0).
        :param lambda_mmr: Facteur de diversification MMR.
                           1.0 = Pure pertinence, 0.0 = Pure diversité.
        """
        self.semantic_weight = semantic_weight
        self.lambda_mmr = lambda_mmr

    def retrieve(self, subject_id: str, query: str, limit: int = 3) -> list[RetrievalResult]:
        """
        Exécute la recherche hybride avec fusion de scores et diversification MMR.
        """
        q = (query or "").strip()
        if not q:
            return []

        try:
            # 1. Récupération d'un pool étendu via search_hybrid (Neon side)
            # On récupère plus de candidats pour laisser de la marge au MMR.
            pool_limit = max(limit * 5, 15)
            candidates = store.search_hybrid(
                subject_id,
                q,
                limit=pool_limit,
                semantic_weight=self.semantic_weight
            )

            if not candidates:
                return []

            # 2. Application de l'algorithme MMR pour diversifier
            # On utilise les embeddings pour calculer la diversité
            diversified = self._apply_mmr(subject_id, q, candidates, limit)

            return diversified

        except Exception as exc:
            log_event(
                "HYBRID_RETRIEVAL_ERROR",
                level="ERROR",
                message=f"Erreur lors de la recherche hybride: {exc}",
                extra={"subject_id": subject_id, "query": q}
            )
            return []

    def _apply_mmr(self, subject_id: str, query: str, candidates: list[dict], k: int) -> list[RetrievalResult]:
        """
        Maximum Marginal Relevance (MMR).
        Sélectionne des documents qui sont pertinents par rapport à la requête,
        mais peu similaires entre eux.
        """
        if not candidates:
            return []

        if len(candidates) <= k:
            return [self._map_to_result(c) for c in candidates]

        # Optimisation : On récupère TOUS les vecteurs des candidats en une seule requête
        from app.services.knowledge.store import _embed, _engine, text

        query_vec = np.array(_embed(query))

        # On récupère les vecteurs en masse pour éviter le problème N+1
        topic_slugs = [cand["topic"] for cand in candidates]

        doc_vecs = []
        with _engine().connect() as conn:
            # On utilise ANY(:slugs) pour récupérer tous les vecteurs d'un coup
            # Note: On trie par ID ou on utilise un mapping pour garantir l'ordre
            res_rows = conn.execute(
                text("SELECT topic_slug, embedding FROM knowledge_sections WHERE topic_slug = ANY(:slugs) AND subject_id = :sid"),
                {"slugs": topic_slugs, "sid": subject_id}
            ).fetchall()

            # Création d'un mapping slug -> vecteur
            vec_map = {}
            for row in res_rows:
                v = row[1]
                if isinstance(v, str):
                    v = np.array([float(x) for x in v.strip("[]").split(",")])
                else:
                    v = np.array(v)
                vec_map[row[0]] = v

        # On reconstruit la liste des vecteurs dans l'ordre des candidats
        for cand in candidates:
            v = vec_map.get(cand["topic"])
            if v is None:
                # Fallback si un vecteur manque (rare)
                doc_vecs.append(np.zeros(len(query_vec)))
            else:
                doc_vecs.append(v)

        selected_indices = []
        unselected_indices = list(range(len(candidates)))

        # Le premier document est toujours le plus pertinent
        first_idx = 0 # candidates est déjà trié par score hybride
        selected_indices.append(first_idx)
        unselected_indices.remove(first_idx)

        while len(selected_indices) < k and unselected_indices:
            best_mmr = -float('inf')
            best_idx = -1

            for idx in unselected_indices:
                # Pertinence (score hybride déjà calculé)
                relevance = candidates[idx]["relevance"]

                # Diversité : similarité max avec les documents déjà sélectionnés
                sim_max = max([np.dot(doc_vecs[idx], doc_vecs[s_idx]) for s_idx in selected_indices])

                # Formule MMR: lambda * relevance - (1 - lambda) * max_similarity
                mmr_score = self.lambda_mmr * relevance - (1 - self.lambda_mmr) * sim_max

                if mmr_score > best_mmr:
                    best_mmr = mmr_score
                    best_idx = idx

            if best_idx != -1:
                selected_indices.append(best_idx)
                unselected_indices.remove(best_idx)
            else:
                break

        return [self._map_to_result(candidates[i]) for i in selected_indices]

    def _map_to_result(self, cand: dict) -> RetrievalResult:
        return {
            "topic": cand["topic"],
            "title": cand["title"],
            "content": cand["content"],
            "source": cand["source"],
            "relevance": cand["relevance"],
            "method": "hybrid"
        }

# Singleton pour usage global
default_hybrid_retriever = HybridRetriever()
