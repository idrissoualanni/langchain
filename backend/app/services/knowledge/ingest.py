# Ingestion du corpus — orchestrateur du pipeline de connaissance.
#
# Chaîne : bytes ( PDF/DOCX/MD ) → Markdown (convert) → frontmatter YAML
# (frontmatter) → sections `##` → chunking par titres 800/100 (chunker)
# → embedding + upsert (store) → réconciliation des sources disparues.
#
# Le pipeline est IDEMPOTENT : ré-importer une page inchangée ne
# réécrit rien ( l'upsert est dédupliqué par (subject_id, topic_slug) et
# par sha256 côté store ). Une section trop longue est découpée en
# plusieurs chunks dont le TITRE reçoit un suffixe « (i/n) » — sans quoi
# les chunks partageraient le même slug et s'écraseraient.
from __future__ import annotations

from pathlib import Path

from app.logging.events import log_event
from app.services.documents import chunker
from app.services.knowledge import convert, frontmatter, store


class KnowledgeIngestor:
    """Ingère des pages ( PDF / DOCX / Markdown ) dans le corpus Neon."""

    def ingest_page(
        self,
        filename: str,
        raw: bytes,
        author: str = "",
        subject_id: str | None = None,
        content_type: str | None = None,
        source_label: str | None = None,
    ) -> dict:
        """Ingère UNE page et retourne le récapitulatif des sections créées.

        Args:
            filename: nom du fichier ( décide du convertisseur ).
            raw: octets bruts.
            author: auteur ( prime sur le frontmatter ).
            subject_id: force la matière ( sinon frontmatter.subject ).
            content_type: MIME déclaré ( indicatif ).
            source_label: force l'identifiant de source ( sinon frontmatter
                .source, sinon « upload/<filename> » ) — sert de clé à la
                réconciliation et au bucket.

        Retourne {filename, subject_id, author, source_label,
        sections_created, sections}. Lève ConvertError ( fichier vide /
        corrompu ) ; les erreurs d'embedding par section sont loggées et
        n'interrompent pas le reste de la page.
        """
        md = convert.to_markdown(filename, raw, content_type)
        fm, body = frontmatter.parse_frontmatter(md)
        subject = subject_id or fm.subject or "general"
        page_author = author or fm.author
        page_source = source_label or fm.source or f"upload/{filename}"

        sections = frontmatter.split_sections_markdown(body)
        if not sections:
            title = fm.title or Path(filename).stem
            sections = [
                (
                    frontmatter.slugify(title) or "_intro",
                    title or Path(filename).stem,
                    (body or md).strip(),
                )
            ]

        created: list[dict] = []
        for _topic_slug, title, content in sections:
            if not content.strip():
                continue
            pieces = chunker.chunk_markdown(content)
            if not pieces:
                continue
            multi = len(pieces) > 1
            for idx, piece in enumerate(pieces, 1):
                part_title = (
                    f"{title} ({idx}/{len(pieces)})" if multi else title
                )
                try:
                    result = store.upsert_section(
                        subject_id=subject,
                        title=part_title,
                        content=piece,
                        source_label=page_source,
                        author=page_author,
                    )
                except Exception as exc:  # noqa: BLE001
                    log_event(
                        "KNOWLEDGE_INGEST_SECTION_FAILED",
                        level="WARNING",
                        message=f"Section {title} non ingérée : {exc}",
                        extra={"subject": subject, "source": page_source},
                    )
                    continue
                created.append(
                    {
                        "id": result["id"],
                        "topic_slug": result["topic_slug"],
                        "title": result["title"],
                    }
                )

        log_event(
            "KNOWLEDGE_INGEST_DONE",
            message=(
                f"Ingestion | {filename} | subject={subject} | "
                f"sections={len(created)}"
            ),
            extra={"operation": "knowledge_ingest", "subject": subject},
        )
        return {
            "filename": filename,
            "subject_id": subject,
            "author": page_author,
            "source_label": page_source,
            "sections_created": len(created),
            "sections": created,
        }

    def reconcile(self, subject_id: str, live_sources: set[str]) -> dict:
        """Supprime les sections/bucket dont la source a disparu.

        `live_sources` = labels des pages ENCORE présentes pour la
        matière. Délègue à store.reconcile_subject_sources ( scoped ).
        """
        return store.reconcile_subject_sources(subject_id, live_sources)


__all__ = ["KnowledgeIngestor"]
