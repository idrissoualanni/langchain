# Conversion PDF / Word → Markdown ( pipeline d'ingestion du corpus ).
#
# Formats supportés :
#   - PDF  : PyMuPDF ( `fitz` ) — extraction par blocs avec heuristique
#            de TITRES ( taille de police > médiane → `## ` ) ;
#   - DOCX : mammoth (`convert_to_markdown`) — Word → Markdown natif ;
#   - MD / TXT / RST : texte brut ( décodage robuste UTF-8 / latin-1 ).
#
# Chaque convertisseur est ISOLÉ : un fichier corrompu lève une
# ConvertError contrôlée, jamais une exception non maîtrisée. Le `.doc`
# binaire ancien n'est PAS supporté ( mammoth ne lit que `.docx` ).
from __future__ import annotations

import re
from pathlib import Path


class ConvertError(Exception):
    """Erreur contrôlée de conversion ( format non supporté / corrompu )."""


# Extensions reconnues par le pipeline d'ingestion.
SUPPORTED_EXTENSIONS = (".md", ".markdown", ".txt", ".rst", ".pdf", ".docx")


def _collapse_blank_lines(md: str) -> str:
    """Fusionne les lignes vides multiples ( Markdown propre )."""
    return re.sub(r"\n{3,}", "\n\n", (md or "").strip()) + "\n"


def pdf_to_markdown(raw: bytes) -> str:
    """Convertisseur PDF → Markdown ( PyMuPDF + heuristique de titres ).

    Les spans dont la taille de police dépasse 1,15× la médiane du
    document deviennent des titres `## `. Les autres lignes restent des
    paragraphes. Lève ConvertError si le PDF est illisible ou sans
    texte extractible ( PDF scanné sans OCR ).
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover
        raise ConvertError(
            "PyMuPDF non installé (pip install pymupdf)"
        ) from exc
    try:
        doc = fitz.open(stream=raw, filetype="pdf")
    except Exception as exc:
        raise ConvertError(f"PDF illisible : {exc}") from exc

    try:
        sizes: list[float] = []
        for page in doc:
            for block in page.get_text("dict").get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if span.get("text", "").strip():
                            sizes.append(float(span.get("size", 0.0)))
        if not sizes:
            raise ConvertError("PDF sans texte extractible (OCR requis ?)")
        sizes.sort()
        # Base = taille « corps » : médiane INFÉRIEURE ( robuste aux
        # petits échantillons où la médiane classique capturerait un
        # titre — ex. [11, 24] → base 11, seuil 12.65 ).
        base = sizes[max(0, (len(sizes) - 1) // 2)] or 1.0
        heading_threshold = base * 1.15

        out: list[str] = []
        for page in doc:
            for block in page.get_text("dict").get("blocks", []):
                for line in block.get("lines", []):
                    spans = [
                        s for s in line.get("spans", []) if s.get("text")
                    ]
                    if not spans:
                        continue
                    text = "".join(
                        s.get("text", "") for s in spans
                    ).strip()
                    if not text:
                        continue
                    max_size = max(float(s.get("size", 0.0)) for s in spans)
                    out.append(
                        f"## {text}"
                        if max_size >= heading_threshold
                        else text
                    )
                out.append("")  # fin de bloc → paragraphe
        return _collapse_blank_lines("\n".join(out))
    finally:
        doc.close()


def docx_to_markdown(raw: bytes) -> str:
    """Convertisseur Word (.docx) → Markdown ( mammoth ).

    mammoth traduit les styles Word en balises Markdown ( titres, listes,
    gras ). Lève ConvertError si mammoth est absent ou le DOCX corrompu.
    """
    try:
        import mammoth
    except ImportError as exc:  # pragma: no cover
        raise ConvertError(
            "mammoth non installé (pip install mammoth)"
        ) from exc
    import io

    try:
        result = mammoth.convert_to_markdown(io.BytesIO(raw))
    except Exception as exc:
        raise ConvertError(f"DOCX illisible : {exc}") from exc
    return _collapse_blank_lines(result.value or "")


def _decode_text(raw: bytes) -> str:
    """Décodage texte robuste ( défaut UTF-8, repli latin-1 )."""
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, ValueError):
            continue
    return raw.decode("latin-1", errors="replace")


def to_markdown(
    filename: str, raw: bytes, content_type: str | None = None
) -> str:
    """Route un upload vers le convertisseur adapté ( PDF / DOCX / texte ).

    Args:
        filename: nom du fichier ( l'extension décide du convertisseur ).
        raw: octets bruts.
        content_type: MIME déclaré ( indice secondaire ).

    Retourne le Markdown. Lève ConvertError ( fichier vide, format
    inconnu, fichier corrompu ).
    """
    if not raw:
        raise ConvertError("Fichier vide")
    ext = Path(filename).suffix.lower()
    ctype = (content_type or "").lower()

    if ext == ".pdf" or "pdf" in ctype:
        return pdf_to_markdown(raw)
    if ext == ".docx" or "wordprocessingml" in ctype:
        return docx_to_markdown(raw)
    if ext in (".md", ".markdown", ".txt", ".rst", "") or "text" in ctype:
        return _decode_text(raw)
    # Format explicitement non supporté ( ex. .doc binaire ) : on tente
    # le décodage texte en dernier recours plutôt que d'échouer.
    return _decode_text(raw)


__all__ = [
    "ConvertError",
    "SUPPORTED_EXTENSIONS",
    "pdf_to_markdown",
    "docx_to_markdown",
    "to_markdown",
]
