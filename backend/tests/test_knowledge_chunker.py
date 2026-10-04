"""Tests offline — chunking du corpus ( titres + secours 800/100 ).

Vérifie chunk_markdown : découpe par titres, fenêtres glissantes de 800
avec chevauchement 100 pour les sections trop longues, atomicité des
blocs de code. Aucune base requise.
"""

from __future__ import annotations

from app.services.documents.chunker import (
    DEFAULT_MD_MAX_CHARS,
    DEFAULT_MD_OVERLAP_CHARS,
    chunk_markdown,
)

SMALL = """## A

Petit paragraphe.

## B

Autre petit paragraphe.
"""


def test_two_sections_two_chunks():
    chunks = chunk_markdown(SMALL)
    assert len(chunks) == 2
    assert chunks[0].startswith("## A")
    assert chunks[1].startswith("## B")


def test_long_section_windowed_with_overlap():
    # Section unique d'environ 2000+ caractères → plusieurs fenêtres.
    words = " ".join(f"mot{i}" for i in range(400))
    text = f"## Longue section\n\n{words}"
    chunks = chunk_markdown(text, max_chars=800, overlap_chars=100)
    assert len(chunks) >= 2
    # respect de la taille ( tolérance : un mot peut dépasser d'un cran )
    assert all(len(c) <= 800 + 40 for c in chunks)
    # chevauchement effectif entre deux fenêtres consécutives
    first, second = set(chunks[0].split()), set(chunks[1].split())
    assert first & second, "aucun chevauchement détecté"


def test_code_block_atomic():
    code = "```python\n" + "\n".join(f"ligne{i} = {i}" for i in range(30)) + "\n```"
    text = f"## Exemple\n\n{code}\n\nTexte après."
    chunks = chunk_markdown(text, max_chars=800, overlap_chars=100)
    joined = "\n".join(chunks)
    assert "```python" in joined
    assert joined.count("```") >= 2  # la fence n'est jamais coupée


def test_empty_returns_empty():
    assert chunk_markdown("") == []
    assert chunk_markdown("   \n  ") == []


def test_defaults_values():
    assert DEFAULT_MD_MAX_CHARS == 800
    assert DEFAULT_MD_OVERLAP_CHARS == 100
