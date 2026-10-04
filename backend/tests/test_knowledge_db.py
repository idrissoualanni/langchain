"""Tests d'intégration — base de connaissance Neon ( pgvector ).

DÉSACTIVÉS par défaut. Opt-in explicite requis :
    KNOWLEDGE_DB_TESTS=1  +  DATABASE_URL=<neon pgvector préparé>

⚠️ Le Neon de staging PARTAGE le projet de la prod : ne lancer ces tests
que contre une base dédiée/préparée. Chaque test utilise un subject_id
UNIQUE et purge ses données ( knowledge_sections/knowledge_files/
subject_definitions ) en teardown — il ne touche aucun autre sujet.

Couvre : ingestion des 3 pages d'exemple ( md / pdf / docx ), propagation
de l'auteur, recherche hybride ( tsvector + cosine ), gating de
validation admin, réconciliation des sources disparues.
"""

from __future__ import annotations

import io
import os
import uuid
import zipfile

import pytest

DB_ENABLED = bool(os.getenv("DATABASE_URL")) and (
    os.getenv("KNOWLEDGE_DB_TESTS") == "1"
)

pytestmark = pytest.mark.skipif(
    not DB_ENABLED,
    reason=(
        "Tests DB désactivés — définir DATABASE_URL ET "
        "KNOWLEDGE_DB_TESTS=1 (base pgvector préparée)."
    ),
)


class _Dim1024Provider:
    """Embedding de test déterministe — dimension 1024 ( cf. colonne )."""

    name = "test-hash-1024"
    dim = 1024

    def embed_text(self, text: str) -> list[float]:
        import hashlib

        vec = [0.0] * 1024
        for tok in (text or "").lower().split():
            h = int.from_bytes(
                hashlib.sha256(tok.encode()).digest()[:4], "little"
            )
            vec[h % 1024] += 1.0
        norm = sum(x * x for x in vec) ** 0.5 or 1.0
        return [x / norm for x in vec]


@pytest.fixture(autouse=True)
def _setup():
    """Installe le provider de test + garantit le schéma ( best effort )."""
    from app.services.context.semantic.provider import set_embedding_provider

    set_embedding_provider(_Dim1024Provider())
    try:
        from app.infrastructure.database.schema import init_schema

        init_schema()
    except Exception:  # noqa: BLE001
        pass
    yield


# ----------------------------------------------------------------------
# Pages d'exemple ( 3 )
# ----------------------------------------------------------------------

_CT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

_DOC = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>
<w:p><w:r><w:t>Lecon de test</w:t></w:r></w:p>
<w:p><w:r><w:t>Contenu de la lecon numero un.</w:t></w:r></w:p>
</w:body>
</w:document>"""


def _page_md(subject: str) -> bytes:
    return f"""---
subject: {subject}
topic: algorithmes
title: Introduction aux algorithmes
author: Pr. Turing
source: upload/algos.md
---
# Introduction

## Definition

Un algorithme est une suite finie d operations.

## Complexite

La complexite mesure la croissance du cout d un algorithme.
""".encode("utf-8")


def _page_pdf() -> bytes:
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Cours PDF", fontsize=24)
    page.insert_text((72, 120), "Un paragraphe de cours en PDF.", fontsize=11)
    raw = doc.tobytes()
    doc.close()
    return raw


def _page_docx() -> bytes:
    pytest.importorskip("mammoth")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/document.xml", _DOC)
    return buf.getvalue()


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _subject_yaml(subject: str) -> str:
    return f"id: {subject}\nname: Test {subject}\n"


def _purge(subject: str) -> None:
    from sqlalchemy import text

    from app.services.knowledge import store

    with store._engine().begin() as conn:
        conn.execute(
            text("DELETE FROM knowledge_sections WHERE subject_id = :s"),
            {"s": subject},
        )
        conn.execute(
            text("DELETE FROM knowledge_files WHERE subject_id = :s"),
            {"s": subject},
        )
        conn.execute(
            text("DELETE FROM subject_definitions WHERE subject_id = :s"),
            {"s": subject},
        )


@pytest.fixture
def subject_id():
    sid = f"test_{uuid.uuid4().hex[:10]}"
    _purge(sid)
    yield sid
    _purge(sid)


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------


def test_ingestion_three_pages(subject_id):
    """Ingère MD + PDF + DOCX ; vérifie sections, auteur et recherche."""
    from app.services.knowledge import store
    from app.services.knowledge.ingest import KnowledgeIngestor

    ing = KnowledgeIngestor()
    r_md = ing.ingest_page(
        "algos.md", _page_md(subject_id), subject_id=subject_id
    )
    assert r_md["sections_created"] >= 2
    assert r_md["author"] == "Pr. Turing"  # auteur venu du frontmatter

    r_pdf = ing.ingest_page("cours.pdf", _page_pdf(), subject_id=subject_id)
    assert r_pdf["sections_created"] >= 1

    r_docx = ing.ingest_page(
        "lecon.docx", _page_docx(), subject_id=subject_id
    )
    assert r_docx["sections_created"] >= 1

    hits = store.search_hybrid(subject_id, "algorithme", limit=5)
    assert hits, "la recherche hybride doit retourner au moins un résultat"
    assert any(h.get("author") == "Pr. Turing" for h in hits)


def test_validation_gating(subject_id):
    """Sujet non validé → non servi ; après validation → servi."""
    from app.services.context.knowledge_retriever import search_knowledge
    from app.services.knowledge import store

    store.upsert_subject_definition(
        subject_id, _subject_yaml(subject_id), status="draft"
    )
    blocked = search_knowledge(subject_id, query="algorithme")
    assert blocked["status"] == "unavailable"

    store.set_subject_status(subject_id, "validated")
    store.upsert_section(
        subject_id, "Algorithmes", "Un algorithme trie une liste.", author="A"
    )
    served = search_knowledge(subject_id, query="algorithme")
    assert served["status"] in ("found", "insufficient")


def test_reconcile_removes_disappeared_sources(subject_id):
    """Réconciliation : les sections d'une source retirée disparaissent."""
    from app.services.knowledge import store

    store.upsert_section(
        subject_id, "Page A", "Contenu A.", source_label="upload/a.md"
    )
    store.upsert_section(
        subject_id, "Page B", "Contenu B.", source_label="upload/b.md"
    )
    assert store.has_subject_corpus(subject_id)

    result = store.reconcile_subject_sources(subject_id, {"upload/b.md"})
    assert result["deleted_sections"] >= 1

    remaining = store.list_topics(subject_id)
    assert "page b" in remaining
    assert "page a" not in remaining


