"""Ré-embedding de user_cognitive_memories vers le provider actif.

Pourquoi : la table a été créée en vector(1536) alors que le provider
actuel produit une autre dimension. Les INSERT échouent, et les vecteurs
existants appartiennent à un ancien espace d'embedding : les comparer à
une requête du nouveau modèle ne veut rien dire. On ne tronque ni ne
complète un vecteur — on ré-encode chaque souvenir depuis son `content`.

Usage (depuis backend/, hors serveur, AUCUN déploiement) :
    python scripts/reembed_cognitive_memories.py            # simulation
    python scripts/reembed_cognitive_memories.py --apply    # écrit

Étapes avec --apply, dans UNE transaction (tout ou rien) :
  1. si la dimension de la colonne diffère : suppression de l'index HNSW,
     ALTER COLUMN embedding TYPE vector(<dim>) USING NULL ;
  2. ajout de embedding_model si absente ;
  3. ré-embedding de chaque ligne + embedding_model ;
  4. recréation de l'index HNSW si la dimension le permet (≤ 2000).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402

from app.infrastructure.database.persistence import _postgres_url  # noqa: E402
from app.services.context.semantic.provider import get_embedding_provider  # noqa: E402
from app.services.memory.cognitive_store import embedding_model_id  # noqa: E402

TABLE = "user_cognitive_memories"
HNSW_INDEX = "idx_cognitive_memories_embedding_hnsw"
HNSW_MAX_DIM = 2000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="écrire (sinon simulation)")
    args = parser.parse_args()

    provider = get_embedding_provider()
    model = embedding_model_id(provider)
    dim = len(provider.embed_text("dimension probe"))
    engine = create_engine(_postgres_url(), pool_pre_ping=True)

    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT atttypmod FROM pg_attribute "
            "WHERE attrelid = to_regclass(:t) AND attname = 'embedding'"
        ), {"t": TABLE}).first()
        if row is None:
            print(f"Table {TABLE} absente — rien à migrer.")
            return 0
        column_dim = int(row[0])
        cols = {
            r[0] for r in conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :t"
            ), {"t": TABLE})
        }
        total = conn.execute(text(f"SELECT count(*) FROM {TABLE}")).scalar()
        stale = total if "embedding_model" not in cols else conn.execute(text(
            f"SELECT count(*) FROM {TABLE} "
            "WHERE embedding_model IS DISTINCT FROM :m OR embedding IS NULL"
        ), {"m": model}).scalar()

        print(f"Provider actif : {model} ({dim} dimensions)")
        print(f"Colonne        : vector({column_dim})")
        print(f"Lignes         : {total} dont {stale} à ré-encoder")
        if column_dim == dim and stale == 0:
            print("Déjà à jour.")
            return 0
        if not args.apply:
            print("Simulation — relancer avec --apply pour écrire.")
            return 0

        if column_dim != dim:
            conn.execute(text(f"DROP INDEX IF EXISTS {HNSW_INDEX}"))
            conn.execute(text(
                f"ALTER TABLE {TABLE} ALTER COLUMN embedding "
                f"TYPE vector({dim}) USING NULL"
            ))
        if "embedding_model" not in cols:
            conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN embedding_model TEXT"))

        rows = conn.execute(text(
            f"SELECT id, content FROM {TABLE} "
            "WHERE embedding_model IS DISTINCT FROM :m OR embedding IS NULL"
        ), {"m": model}).fetchall()
        for i, (mid, content) in enumerate(rows, 1):
            vec = provider.embed_text(content)
            conn.execute(text(
                f"UPDATE {TABLE} SET embedding = :e, embedding_model = :m WHERE id = :id"
            ), {"e": f"[{','.join(map(str, vec))}]", "m": model, "id": mid})
            if i % 50 == 0:
                print(f"  {i}/{len(rows)}")

        if column_dim != dim and dim <= HNSW_MAX_DIM:
            conn.execute(text(
                f"CREATE INDEX IF NOT EXISTS {HNSW_INDEX} ON {TABLE} "
                "USING hnsw (embedding vector_cosine_ops)"
            ))
        print(f"Terminé : {len(rows)} lignes ré-encodées.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
