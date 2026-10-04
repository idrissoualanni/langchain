"""Tests offline — projection PCA 3D et arêtes kNN ( visualisation ).

Vérifie le calcul numpy ( aucune base requise ) : dimension des
coordonnées, ratio de variance, arêtes kNN dédupliquées.
"""

from __future__ import annotations

from app.services.knowledge.viz import knn_edges, project_embeddings_3d

# 6 vecteurs en dimension 8, groupes distincts → structure attendue.
VECTORS = [
    [1.0, 0.9, 0.1, 0.0, 0.2, 0.1, 0.0, 0.0],
    [1.1, 1.0, 0.0, 0.1, 0.1, 0.0, 0.1, 0.0],
    [0.0, 0.1, 1.0, 0.9, 0.0, 0.2, 0.0, 0.1],
    [0.1, 0.0, 1.1, 1.0, 0.1, 0.0, 0.0, 0.1],
    [0.0, 0.0, 0.1, 0.0, 1.0, 0.9, 1.0, 0.8],
    [0.1, 0.1, 0.0, 0.1, 0.9, 1.0, 1.1, 0.9],
]


def test_projection_shape_and_variance():
    coords, ratio = project_embeddings_3d(VECTORS)
    assert len(coords) == len(VECTORS)
    assert all(len(xyz) == 3 for xyz in coords)
    # ratio : 3 valeurs, chacune dans [0,1]
    assert len(ratio) == 3
    assert all(0.0 <= r <= 1.0 for r in ratio)


def test_projection_empty():
    assert project_embeddings_3d([]) == ([], [])


def test_knn_edges_undirected_dedup():
    coords, _ = project_embeddings_3d(VECTORS)
    edges = knn_edges(coords, k=2)
    assert edges, "des arêtes sont attendues"
    seen = set()
    for e in edges:
        key = (min(e["source"], e["target"]), max(e["source"], e["target"]))
        assert key not in seen, "arête dupliquée"
        seen.add(key)
        assert e["distance"] >= 0.0


def test_knn_edges_guard_large_n():
    # Au-delà du seuil, aucune arête émise ( coût quadratique évité ).
    big = [[float(i), float(i % 7), float(i % 3)] for i in range(1600)]
    assert knn_edges(big, k=3) == []
