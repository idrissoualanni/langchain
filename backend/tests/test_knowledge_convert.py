"""Tests offline — conversion PDF / Word → Markdown.

Génère un PDF ( PyMuPDF ) et un DOCX minimal ( zip OOXML ) à la volée,
puis vérifie `to_markdown`. Les tests qui exigent une dépendance absente
( mammoth / pymupdf ) sont SKIPPÉS proprement.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from app.services.knowledge import convert

# ----------------------------------------------------------------------
# Fixtures générées à la volée
# ----------------------------------------------------------------------


def _make_pdf() -> bytes:
    import fitz  # PyMuPDF

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Titre", fontsize=24)
    page.insert_text((72, 120), "Corps du paragraphe.", fontsize=11)
    raw = doc.tobytes()
    doc.close()
    return raw


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
<w:p><w:r><w:t>Contenu de la lecon.</w:t></w:r></w:p>
</w:body>
</w:document>"""


def _make_docx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/document.xml", _DOC)
    return buf.getvalue()


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------


def test_text_passthrough():
    assert convert.to_markdown("a.md", b"# Hi") == "# Hi"
    assert convert.to_markdown("a.txt", "café".encode("latin-1")) == "café"


def test_empty_raises():
    with pytest.raises(convert.ConvertError):
        convert.to_markdown("a.md", b"")


def test_pdf_to_markdown():
    pytest.importorskip("fitz")
    md = convert.pdf_to_markdown(_make_pdf())
    assert "## Titre" in md  # titre détecté par la taille de police
    assert "Corps du paragraphe." in md


def test_docx_to_markdown():
    pytest.importorskip("mammoth")
    md = convert.docx_to_markdown(_make_docx())
    assert "Lecon de test" in md
    assert "Contenu de la lecon." in md


def test_to_markdown_routes_by_extension():
    pytest.importorskip("fitz")
    md = convert.to_markdown("cours.pdf", _make_pdf(), "application/pdf")
    assert "Titre" in md
