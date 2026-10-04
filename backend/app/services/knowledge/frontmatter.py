# Frontmatter YAML — en-tête `---…---` d'une page Markdown source.
#
# Le format d'import du corpus est une page Markdown dont l'en-tête YAML
# décrit son appartenance :
#
#   ---
#   subject: python
#   topic: fonctions
#   title: Les fonctions
#   author: Pr. X
#   status: draft        # indicatif — le statut RÉEL est géré par l'admin
#   ---
#   # Les fonctions
#   ## Définition
#   ...
#
# `parse_frontmatter` sépare l'en-tête du corps et le valide via
# ChunkFrontmatter ( Pydantic ). `split_sections_markdown` découpe le
# corps en sections `##` → (topic_slug, title, body).
from __future__ import annotations

import re
import unicodedata

from app.schemas.knowledge import ChunkFrontmatter

# En-tête : `---` … `---` en tout début de document.
_FRONTMATTER_RE = re.compile(
    r"^\ufeff?\s*---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL
)
# Titres de niveau 2 (`## …`) — bornes de section du corpus.
_H2_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)


def slugify(value: str) -> str:
    """Slug accent-less minuscule — même règle que le store/ingestion.

    « Définition » → « definition ». Cohérent entre la migration, le
    découpage `##` et la recherche exacte par slug.
    """
    normalized = "".join(
        c
        for c in unicodedata.normalize("NFKD", value or "")
        if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", normalized).strip().lower()


def parse_frontmatter(md: str) -> tuple[ChunkFrontmatter, str]:
    """Sépare l'en-tête YAML du corps Markdown.

    Retourne (ChunkFrontmatter, body). Sans en-tête ( ou en-tête YAML
    invalide ), retourne un ChunkFrontmatter vide et le texte intégral :
    l'ingestion ne doit JAMAIS échouer faute de frontmatter.
    """
    import yaml

    text = md or ""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return ChunkFrontmatter(), text
    raw_yaml, body = match.group(1), match.group(2)
    try:
        data = yaml.safe_load(raw_yaml) or {}
    except Exception:  # noqa: BLE001 — frontmatter illisible ≠ échec
        data = {}
    if not isinstance(data, dict):
        data = {}
    try:
        fm = ChunkFrontmatter(**data)
    except Exception:  # noqa: BLE001 — champs invalides → best effort
        fm = ChunkFrontmatter()
    return fm, body


def split_sections_markdown(md: str) -> list[tuple[str, str, str]]:
    """Découpe un corps Markdown en sections `## Titre`.

    Retourne [(topic_slug, title, body)] hors en-tête YAML. Le texte
    précédant le premier `##` devient une section « _intro » ( jamais
    utilisée comme section d'exercice, comme la migration historique ).
    Une page sans `##` produit UNE section sous le titre fourni par
    l'appelant ( repli géré par l'ingestor ).
    """
    text = md or ""
    sections: list[tuple[str, str, str]] = []
    current_topic = "_intro"
    current_title = "(introduction)"
    buf: list[str] = []

    def _flush() -> None:
        nonlocal buf
        body = "\n".join(buf).strip()
        if body:
            sections.append((current_topic, current_title, body))
        buf = []

    for line in text.splitlines():
        m = _H2_RE.match(line)
        if m:
            _flush()
            current_title = m.group(1).strip()
            current_topic = slugify(current_title)
        else:
            buf.append(line)
    _flush()
    return sections


__all__ = ["slugify", "parse_frontmatter", "split_sections_markdown"]
