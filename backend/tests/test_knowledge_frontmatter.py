"""Tests offline — frontmatter YAML des pages source (knowledge).

Vérifie parse_frontmatter ( séparation en-tête/corps, validation Pydantic )
et split_sections_markdown ( découpe `##`). Aucune base requise.
"""

from __future__ import annotations

from app.services.knowledge.frontmatter import (
    parse_frontmatter,
    slugify,
    split_sections_markdown,
)

PAGE = """---
subject: python
topic: fonctions
title: Les fonctions
author: Pr. X
status: draft
---
# Les fonctions

## Définition

Une fonction regroupe des instructions réutilisables.

## Paramètres

Une fonction peut prendre des paramètres.
"""


def test_frontmatter_parsed():
    fm, body = parse_frontmatter(PAGE)
    assert fm.subject == "python"
    assert fm.topic == "fonctions"
    assert fm.author == "Pr. X"
    assert fm.title == "Les fonctions"
    # le corps ne contient plus l'en-tête
    assert body.lstrip().startswith("# Les fonctions")
    assert "subject:" not in body


def test_frontmatter_absent_is_safe():
    fm, body = parse_frontmatter("# Titre\n\nCorps sans en-tête.")
    assert fm.subject == ""
    assert fm.author == ""
    assert body == "# Titre\n\nCorps sans en-tête."


def test_frontmatter_invalid_status_defaults():
    # statut hors vocabulaire → best effort ( défaut draft, pas d'échec )
    fm, _ = parse_frontmatter("---\nsubject: x\nstatus: invalid\n---\nbody")
    assert fm.status == "draft"


def test_split_sections_markdown():
    _, body = parse_frontmatter(PAGE)
    sections = split_sections_markdown(body)
    slugs = [s[0] for s in sections]
    titles = [s[1] for s in sections]
    assert "definition" in slugs
    assert "parametres" in slugs
    assert "Définition" in titles


def test_slugify():
    assert slugify("Définition Générale") == "definition generale"
