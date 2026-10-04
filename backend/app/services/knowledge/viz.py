# Visualisation 3D des chunks vectorisés — projection PCA ( numpy SVD ).
#
# Le corpus ( attention : embeddings de dimension ~1024 ) est projeté sur
# 3 composantes principales ( PCA ) pour être rendu en nuage de points
# ( Three.js `Points` ), avec des arêtes kNN ( `Line` ) et des sphères
# optionnelles ( `Mesh` ) côté frontend.
#
# Le calcul PCA vit ICI ( numpy ) et non en JavaScript : Three.js n'a pas
# de PCA, et la projection côté serveur garantit que tous les clients
# voient EXACTEMENT le même espace. Le module ne lève jamais : une viz
# indisponible renvoie un graphe vide plutôt que de casser l'admin.
from __future__ import annotations

# Au-delà de ce nombre de points, on n'émet AUCUNE arête kNN ( coût
# O(n²) ) — le nuage reste affiché, les liaisons disparaissent.
_MAX_EDGE_POINTS = 1500


def project_embeddings_3d(
    vectors: list[list[float]],
) -> tuple[list[list[float]], list[float]]:
    """Projette des vecteurs N-dim en 3D par PCA ( SVD tronquée ).

    Centrage puis décomposition en valeurs singulières : les 3 premières
    composantes principales donnent les coordonnées 3D. Retourne
    (coordinates, explained_variance_ratio) — ratio = part de variance
    portée par chaque axe ( pour légender le graphique ). Liste vide en
    entrée → ([], []).
    """
    import numpy as np

    if not vectors:
        return [], []
    X = np.asarray(vectors, dtype=float)
    if X.ndim != 2 or X.shape[0] == 0 or X.shape[1] == 0:
        return [], []

    mean = X.mean(axis=0)
    Xc = X - mean
    k = min(3, X.shape[0], X.shape[1])
    # SVD tronquée : U (n×k), S (k,), Vt (k×d)
    U, S, _Vt = np.linalg.svd(Xc, full_matrices=False)
    coords = U[:, :k] * S[:k]
    if k < 3:  # pad à 3 colonnes ( cas dégénéré : peu de points/dims )
        coords = np.hstack(
            [coords, np.zeros((coords.shape[0], 3 - k))]
        )

    var = S**2
    total = float(var.sum()) or 1.0
    ratio = (var[:k] / total).tolist()
    return coords.tolist(), [round(r, 4) for r in ratio]


def knn_edges(
    coords: list[list[float]], k: int = 3
) -> list[dict]:
    """Arêtes kNN entre points projetés ( voisinage sémantique ).

    Pour chaque point, les `k` plus proches voisins ( distance
    euclidienne en 3D ) ; les arêtes sont dédupliquées ( non orientées ).
    Au-delà de _MAX_EDGE_POINTS points, retourne [] ( coût quadratique ).
    """
    import numpy as np

    n = len(coords)
    if n < 2 or n > _MAX_EDGE_POINTS:
        return []
    P = np.asarray(coords, dtype=float)
    edges: dict[tuple[int, int], float] = {}
    for i in range(n):
        d = np.linalg.norm(P - P[i], axis=1)
        order = np.argsort(d)[1 : k + 1]  # exclut soi-même
        for j in order:
            a, b = (i, int(j)) if i < int(j) else (int(j), i)
            dist = float(np.linalg.norm(P[a] - P[b]))
            edges[(a, b)] = dist
    return [
        {"source": a, "target": b, "distance": round(dist, 4)}
        for (a, b), dist in edges.items()
    ]


def get_chunk_viz(
    subject_id: str | None = None, limit: int = 2000
) -> dict:
    """Charge les vecteurs du corpus et construit le graphe 3D.

    Délègue le chargement à store.list_chunk_vectors ( filtré par sujet
    optionnel ), puis projette en 3D ( PCA ) et calcule les arêtes kNN.
    Retourne un dict compatible ChunkVizResponse. Ne lève jamais.
    """
    from app.services.knowledge import store

    try:
        rows = store.list_chunk_vectors(subject_id, limit)
    except Exception:  # noqa: BLE001 — viz indisponible ≠ crash admin
        rows = []

    vectors = [r.get("embedding") or [] for r in rows]
    vectors = [v for v in vectors if v]
    dim = len(vectors[0]) if vectors else 0

    coords, ratio = project_embeddings_3d(vectors)
    points = []
    for row, xyz in zip(rows, coords):
        points.append(
            {
                "id": row["id"],
                "x": float(xyz[0]),
                "y": float(xyz[1]),
                "z": float(xyz[2]),
                "subject_id": row.get("subject_id", ""),
                "topic_slug": row.get("topic_slug", ""),
                "title": row.get("title", ""),
                "author": row.get("author", ""),
                "source_label": row.get("source_label", ""),
            }
        )

    return {
        "projection": "pca3d",
        "points": points,
        "edges": knn_edges(coords, k=3),
        "count": len(points),
        "dim": dim,
        "explained_variance": ratio,
        "subject_id": subject_id,
    }


__all__ = ["project_embeddings_3d", "knn_edges", "get_chunk_viz"]
