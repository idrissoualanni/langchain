# Documents V10 — extraction de texte à l'upload.
#
# Formats supportés (mission) :
#   md / markdown / txt / rst  : texte brut UTF-8 (décodage robuste)
#   pdf                          : extraction PyMuPDF (fitz)
#
# Chaque extracteur est ISOLÉ : un PDF corrompu → PDFExtractError
# contrôlé (422), jamais une exception non maîtrisée.
from __future__ import annotations

from pathlib import Path

# Extensions reconnues (schémas ALLOWED_EXTENSIONS aligné).
_EXT_MAP = {
    ".md": "text/plain",
    ".markdown": "text/plain",
    ".txt": "text/plain",
    ".rst": "text/plain",
    ".pdf": "application/pdf",
}

MAX_FILE_BYTES = 2_000_000  # aligné DocumentUploadCreate.content max


class DocumentExtractError(Exception):
    """Erreur contrôlée d'extraction (format non supporté / corrompu)."""


def infer_content_type(filename: str) -> str:
    """MIME déclaré depuis l'extension (ou text/plain par défaut)."""
    ext = Path(filename).suffix.lower()
    return _EXT_MAP.get(ext, "text/plain")


def extract_text(
    filename: str, raw: bytes, content_type: str | None = None
) -> str:
    """Extrait le texte d'un upload (bytes) en str exploitable.

    Retourne str ; une erreur → DocumentExtractError.
    """
    if not raw:
        raise DocumentExtractError("Fichier vide")
    ctype = (content_type or infer_content_type(filename)).lower()
    ext = Path(filename).suffix.lower()

    if ext == ".pdf" or "pdf" in ctype:
        return _extract_pdf(raw)

    # texte brut : décodage robuste (défaut UTF-8, repli latin-1)
    return _decode_text(raw)


def _decode_text(raw: bytes) -> str:
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, ValueError):
            continue
    return raw.decode("latin-1", errors="replace")


def _extract_pdf(raw: bytes) -> str:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover
        raise DocumentExtractError(
            "PyMuPDF non installé (pip install pymupdf)"
        ) from exc
    try:
        doc = fitz.open(stream=raw, filetype="pdf")
    except Exception as exc:
        raise DocumentExtractError(f"PDF illisible : {exc}") from exc
    try:
        pages = []
        for page in doc:
            pages.append(page.get_text("text"))
        return "\n\n".join(p for p in pages if p and p.strip())
    finally:
        doc.close()


__all__ = [
    "MAX_FILE_BYTES",
    "DocumentExtractError",
    "extract_text",
    "infer_content_type",
]