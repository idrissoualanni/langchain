# Migration ONE-OFF du corpus knowledge → Neon ( 3 phases ).
#
# Mission « aucune base de connaissance codée en dur dans le projet » :
#   1. SECTIONS  — découpe « ## Titre » + vectorisation ( provider actif
#      embeddings.yaml, local qwen3-embedding:0.6b ) → knowledge_sections ;
#      le subject_id est résolu via les définitions YAML ( knowledge.
#      sources ) — PAS le premier composant du chemin ;
#   2. BUCKET    — chaque fichier .md SOURCE est stocké brut dans
#      knowledge_files ( l'original restituable, idempotent par sha256 ) ;
#   3. MATIÈRES  — les YAML de définitions sont seedés dans
#      subject_definitions ( le registry les charge au démarrage ).
#
# Usage :
#   python scripts/migrate_knowledge_neon.py \
#       --dir <dossier_corpus> [--definitions <dir_yaml>] [--force]
#
# Idempotent : seules les sections/fichiers dont le sha256 a changé sont
# retraités ; --force ré-embedde tout ( changement de modèle ).
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.infrastructure.database.persistence import _postgres_url  # noqa: E402
from app.logging.events import log_event  # noqa: E402


def _strip_accents(value: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(c)
    )


def _split_sections(content: str) -> list[tuple[str, str, str]]:
    """[(topic_slug, title_brut, contenu)] — découpe sur « ## Titre »."""
    sections: list[tuple[str, str, str]] = []
    current_topic = "_intro"
    current_title = "(introduction)"
    current_lines: list[str] = []
    for line in content.splitlines():
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            if current_lines:
                sections.append(
                    (current_topic, current_title, "\n".join(current_lines).strip())
                )
            current_title = m.group(1).strip()
            current_topic = _strip_accents(current_title.lower())
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append(
            (current_topic, current_title, "\n".join(current_lines).strip())
        )
    return [(t, ti, c) for t, ti, c in sections if c]


def _subject_map(definitions_dir: Path | None) -> dict[str, str]:
    """{chemin_source_sans_ext} → subject_id du registry.

    Chaque YAML déclare knowledge.sources: ['informatique/python/basics', …]
    — le chemin du fichier relatif au corpus EST la source.
    """
    mapping: dict[str, str] = {}
    if definitions_dir is None or not definitions_dir.exists():
        return mapping
    for yml in sorted(definitions_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        sid = data.get("id")
        if not sid:
            continue
        for src in (data.get("knowledge") or {}).get("sources", []):
            mapping[str(src)] = sid
    return mapping


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True, help="Dossier du corpus .md")
    parser.add_argument(
        "--definitions",
        help="Dossier des YAML de matières ( phase 3 — seed )",
    )
    parser.add_argument(
        "--force", action="store_true", help="Ré-embedder tout"
    )
    parser.add_argument(
        "--no-sections", action="store_true", help="Sauter la phase sections"
    )
    args = parser.parse_args()

    root = Path(args.dir).resolve()
    if not root.exists():
        print(f"ERREUR: {root} introuvable")
        return 1
    definitions_dir = (
        Path(args.definitions).resolve() if args.definitions else None
    )
    subject_map = _subject_map(definitions_dir)
    print(f"mapping matières: {len(subject_map)} sources")

    engine = create_engine(_postgres_url(), pool_pre_ping=True)

    files = sorted(root.rglob("*.md"))
    print(f"{len(files)} fichiers .md")

    # ---------------- Phase 2 : BUCKET ( toujours ) ----------------
    # Double écriture :
    #   - knowledge_files : table structurée ( sync sections ↔ sources ) ;
    #   - object_storage  : le BUCKET assets existant ( kind='knowledge',
    #     user_id='system' ) — visible depuis l'admin / le stockage.
    from app.services.storage.object_store import put_object

    bucket_written = 0
    bucket_objects = 0
    with engine.begin() as conn:
        for path in files:
            rel = path.relative_to(root).as_posix()
            try:
                content = path.read_text(encoding="utf-8")
            except Exception as exc:
                print(f"  LECTURE KO {rel}: {exc}")
                continue
            if not content.strip():
                continue
            sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
            sid = subject_map.get(
                rel.removesuffix(".md"), rel.split("/")[0]
            )
            row = conn.execute(
                text("SELECT sha256 FROM knowledge_files WHERE path = :p"),
                {"p": rel},
            ).first()
            if row is not None and row[0] == sha and not args.force:
                continue
            conn.execute(
                text(
                    "INSERT INTO knowledge_files "
                    "(path, subject_id, content, sha256, created_at) "
                    "VALUES (:p, :sid, :c, :sha, :created) "
                    "ON CONFLICT (path) DO UPDATE SET "
                    "subject_id = EXCLUDED.subject_id, "
                    "content = EXCLUDED.content, sha256 = EXCLUDED.sha256"
                ),
                {
                    "p": rel,
                    "sid": sid,
                    "c": content,
                    "sha": sha,
                    "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                },
            )
            bucket_written += 1
    # object_storage — en dehors de la transaction ci-dessus ( le
    # put_object gère sa propre transaction + S3 éventuel ).
    for path in files:
        rel = path.relative_to(root).as_posix()
        try:
            data = path.read_bytes()
        except Exception:
            continue
        try:
            put_object(
                user_id="system",
                kind="knowledge",
                filename=rel,
                mime="text/markdown",
                data=data,
            )
            bucket_objects += 1
        except Exception as exc:
            print(f"  BUCKET OBJET KO {rel}: {exc}")
    print(
        f"BUCKET: {bucket_written} knowledge_files écrites, "
        f"{bucket_objects} objets object_storage"
    )

    # ------------- Phase 3 : SEED définitions matières -------------
    seeded = 0
    if definitions_dir and definitions_dir.exists():
        with engine.begin() as conn:
            for yml in sorted(definitions_dir.glob("*.yaml")):
                raw = yml.read_text(encoding="utf-8")
                try:
                    data = yaml.safe_load(raw) or {}
                except Exception as exc:
                    print(f"  YAML KO {yml.name}: {exc}")
                    continue
                sid = data.get("id")
                if not sid:
                    continue
                sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                row = conn.execute(
                    text(
                        "SELECT sha256 FROM subject_definitions "
                        "WHERE subject_id = :s"
                    ),
                    {"s": sid},
                ).first()
                if row is not None and row[0] == sha and not args.force:
                    continue
                conn.execute(
                    text(
                        "INSERT INTO subject_definitions "
                        "(subject_id, yaml, sha256, updated_at) "
                        "VALUES (:s, :y, :sha, :u) "
                        "ON CONFLICT (subject_id) DO UPDATE SET "
                        "yaml = EXCLUDED.yaml, sha256 = EXCLUDED.sha256, "
                        "updated_at = EXCLUDED.updated_at"
                    ),
                    {
                        "s": sid,
                        "y": raw,
                        "sha": sha,
                        "u": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    },
                )
                seeded += 1
        print(f"MATIÈRES: {seeded} définitions seedées")

    # --------------- Phase 1 : SECTIONS vectorisées ---------------
    if args.no_sections:
        print("sections: sautée (--no-sections)")
        return 0

    from app.services.context.semantic.provider import get_embedding_provider

    provider = get_embedding_provider()
    t0 = time.time()
    probe = provider.embed_text("warmup")
    print(f"Provider OK ( dim={len(probe)} ), warm-up {time.time()-t0:.1f}s")

    batch: list[tuple[str, str, str, str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for path in files:
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if not content.strip():
            continue
        rel = path.relative_to(root)
        rel_posix = rel.as_posix()
        # subject_id : YAML knowledge.sources d'abord, sinon 1er dossier
        subject_id = subject_map.get(rel_posix.removesuffix(".md")) or rel.parts[0]
        sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        for topic_slug, title, body in _split_sections(content):
            key = (subject_id, topic_slug)
            if key in seen:
                continue
            seen.add(key)
            batch.append(
                (
                    subject_id,
                    topic_slug,
                    title,
                    body,
                    sha,
                    f"{rel.parent.name}/{rel.stem}",
                )
            )
    print(f"{len(batch)} sections à considérer")

    with engine.connect() as conn:
        existing = {
            (r[0], r[1]): r[2]
            for r in conn.execute(
                text(
                    "SELECT subject_id, topic_slug, source_sha "
                    "FROM knowledge_sections"
                )
            ).fetchall()
        }

    to_embed = [
        meta
        for meta in batch
        if args.force or existing.get((meta[0], meta[1])) != meta[4]
    ]
    print(
        f"à embedder: {len(to_embed)} | "
        f"inchangées (skipped): {len(batch) - len(to_embed)}"
    )

    inserted = 0
    if to_embed:
        vectors: list[list[float]] = []
        for i, meta in enumerate(to_embed, 1):
            sid, topic, title, body, sha, label = meta
            try:
                vectors.append(provider.embed_text(f"{title}\n{body[:4000]}"))
            except Exception as exc:
                print(f"ABORT: embedding KO sur {sid}/{topic}: {exc}")
                return 1
            if i % 20 == 0 or i == len(to_embed):
                print(f"  embeddings {i}/{len(to_embed)}")

        with engine.begin() as conn:
            for meta, vec in zip(to_embed, vectors):
                sid, topic, title, body, sha, label = meta
                conn.execute(
                    text(
                        "DELETE FROM knowledge_sections "
                        "WHERE subject_id = :sid AND topic_slug = :slug"
                    ),
                    {"sid": sid, "slug": topic},
                )
                conn.execute(
                    text(
                        "INSERT INTO knowledge_sections "
                        "(subject_id, topic_slug, title, content, embedding, "
                        " source_sha, created_at, source_label) "
                        "VALUES (:sid, :slug, :title, :content, "
                        " CAST(:qv AS vector), :sha, :created, :label)"
                    ),
                    {
                        "sid": sid,
                        "slug": topic,
                        "title": title,
                        "content": body,
                        "qv": "[" + ",".join(f"{x:.7f}" for x in vec) + "]",
                        "sha": sha,
                        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "label": label,
                    },
                )
                inserted += 1

    with engine.connect() as conn:
        total, embedded_n = conn.execute(
            text(
                "SELECT COUNT(*), COUNT(*) FILTER (WHERE embedding IS NOT NULL) "
                "FROM knowledge_sections"
            )
        ).fetchone()
        subjects_n = conn.execute(
            text("SELECT COUNT(DISTINCT subject_id) FROM knowledge_sections")
        ).scalar_one()
        files_n = conn.execute(
            text("SELECT COUNT(*) FROM knowledge_files")
        ).scalar_one()
        defs_n = conn.execute(
            text("SELECT COUNT(*) FROM subject_definitions")
        ).scalar_one()

    print(
        f"TERMINÉ: sections insérées={inserted} | Neon: {total} sections / "
        f"{embedded_n} vectorisées / {subjects_n} sujets | "
        f"{files_n} fichiers bucket | {defs_n} matières"
    )
    log_event(
        "KNOWLEDGE_MIGRATION_DONE",
        message=(
            f"Migration corpus → Neon: {inserted} sections, {files_n} fichiers, "
            f"{defs_n} matières"
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
