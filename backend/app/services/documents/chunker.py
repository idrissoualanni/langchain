# Chunker V10 — découpe un document en chunks cohérents.
#
# Règles :
#   - taille cible ~500 tokens (estimation ~4 chars/token) ;
#   - chevauchement ~50 tokens entre chunks consécutifs (contexte) ;
#   - les titres Markdown (##…####) commencent un NOUVEAU chunk
#     (bornes sémantiques naturelles) ;
#   - les blocs code (```) sont ATOMIQUES : jamais découpés, ils
#     ouvrent un nouveau chunk s'ils ne tiennent pas dans le courant ;
#   - jamais de chunk vide.
from __future__ import annotations

import re

DEFAULT_CHUNK_TOKENS = 500
DEFAULT_OVERLAP_TOKENS = 50
_CHARS_PER_TOKEN = 4
_CODE_BLOCK_RE = re.compile(
    r"^```[^\n]*\n.*?^```[^\n]*$", re.MULTILINE | re.DOTALL
)
_HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$", re.MULTILINE)


def _approx_tokens(text: str) -> int:
    """Estimation tokens (chars / 4) — suffisante pour le chunking."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _split_units(text: str) -> list[tuple[str, bool, bool]]:
    """Découpe le texte en unités (text, is_code, is_heading).

    1. Les blocs ```…``` deviennent des unités atomic code.
    2. Les titres ## Rendent un nouveau titre une unité (heading).
    3. Le reste est découpé en paragraphes (ligne vide).
    """
    units: list[tuple[str, bool, bool]] = []

    # Étape 1 — extraire les blocs code protégés (placeholder).
    code_blocks: list[str] = []
    def _protect(match: re.Match) -> str:
        code_blocks.append(match.group(0))
        return f"\u0000CODE{len(code_blocks)-1}\u0000"
    protected = _CODE_BLOCK_RE.sub(_protect, text)

    # Étape 2 — découpage aux titres.
    parts: list[tuple[str, bool, bool]] = []
    pos = 0
    for m in _HEADING_RE.finditer(protected):
        if m.start() > pos:
            parts.append((protected[pos:m.start()], False, False))
        parts.append((m.group(0), False, True))
        pos = m.end()
    if pos < len(protected):
        parts.append((protected[pos:], False, False))

    # Étape 3 — paragraphes dans les parties non-titre, réinjection code.
    for content, is_code, is_heading in parts:
        if is_heading:
            if content.strip():
                units.append((content.strip(), False, True))
            continue
        if not content.strip():
            continue

        def _restore(piece: str) -> str:
            return re.sub(r"\u0000CODE(\d+)\u0000",
                          lambda mm: code_blocks[int(mm.group(1))],
                          piece)

        for paragraph in re.split(r"\n\s*\n", content):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            if "\u0000CODE" in paragraph:
                # contient un ou des blocs code → séparer
                for token in re.split(r"(\u0000CODE\d+\u0000)", paragraph):
                    token = token.strip()
                    if not token:
                        continue
                    if re.fullmatch(r"\u0000CODE\d+\u0000", token):
                        units.append((_restore(token), True, False))
                    else:
                        units.append((_restore(token), False, False))
            else:
                units.append((paragraph, False, False))
    return units


def _push_windowed(
    chunks: list[str], text: str, chunk_tokens: int, overlap_tokens: int
) -> None:
    """Découpe un morceau seul trop long en fenêtres glissantes.

    Stratégie : chaque fenêtre couvre `chunk_tokens` ; on avance de
    (chunk_tokens - overlap_tokens) entre deux fenêtres (repli sur
    les mots précédents = chevauchement effectif).
    """
    words = text.split()
    chunk_chars = chunk_tokens * _CHARS_PER_TOKEN
    step_words = max(1, (chunk_tokens - overlap_tokens) * _CHARS_PER_TOKEN // 4)
    start = 0
    while start < len(words):
        end = start
        size = 0
        while end < len(words) and size + len(words[end]) + 1 <= chunk_chars:
            size += len(words[end]) + 1
            end += 1
        if end == start:
            end = start + 1
        piece = " ".join(words[start:end]).strip()
        if piece:
            chunks.append(piece)
        if end >= len(words):
            break
        start = min(end - 1, start + step_words)


def chunk_text(
    text: str,
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[str]:
    """Découpe un texte en chunks (list[str])."""
    if not text or not text.strip():
        return []

    units = _split_units(text)
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    def _flush() -> None:
        nonlocal current, current_tokens
        joined = "\n\n".join(current).strip()
        if joined:
            chunks.append(joined)
        current = []
        current_tokens = 0

    for unit, is_code, is_heading in units:
        utok = _approx_tokens(unit)
        if is_code:
            # bloc code atomique : jamais découpé
            if current_tokens + utok > chunk_tokens and current:
                _flush()
            current.append(unit)
            current_tokens += utok
        elif is_heading:
            # un titre ouvre un nouveau chunk (sauf si vide)
            if current:
                _flush()
            current.append(unit)
            current_tokens = utok
        else:
            if current_tokens + utok <= chunk_tokens:
                current.append(unit)
                current_tokens += utok
            elif not current:
                # seul morceau + trop grand → fenêtres
                _push_windowed(chunks, unit, chunk_tokens, overlap_tokens)
            else:
                _flush()
                if _approx_tokens(unit) <= chunk_tokens:
                    current.append(unit)
                    current_tokens = _approx_tokens(unit)
                else:
                    _push_windowed(chunks, unit, chunk_tokens, overlap_tokens)

    if current:
        joined = "\n\n".join(current).strip()
        if joined:
            chunks.append(joined)
    return chunks


# ----------------------------------------------------------------------
# Chunking du CORPUS de connaissance ( découpage par titres ).
#
# Règle mission : un titre Markdown ( ##…#### ) démarre une section ; si
# la section dépasse `max_chars` caractères, elle est découpée en FENÊTRES
# GLISSANTES de `max_chars` avec chevauchement `overlap_chars` ( secours
# 800 / 100 ). Les blocs de code restent ATOMIQUES ( jamais coupés ).
# ----------------------------------------------------------------------

DEFAULT_MD_MAX_CHARS = 800
DEFAULT_MD_OVERLAP_CHARS = 100


def _window_chars(
    text: str, max_chars: int, overlap_chars: int
) -> list[str]:
    """Fenêtres glissantes par MOTS respectant max_chars / overlap_chars.

    On avance d'environ (max_chars - overlap_chars) caractères entre deux
    fenêtres ; le repli sur les mots précédents matérialise le
    chevauchement. Un mot seul plus long que max_chars n'est jamais coupé.
    """
    words = text.split()
    if not words:
        return []
    step = max(1, max_chars - overlap_chars)
    out: list[str] = []
    start = 0
    n = len(words)
    while start < n:
        size = 0
        end = start
        while end < n and size + len(words[end]) + 1 <= max_chars:
            size += len(words[end]) + 1
            end += 1
        if end == start:  # mot unique trop long → au moins un mot
            end = start + 1
        piece = " ".join(words[start:end]).strip()
        if piece:
            out.append(piece)
        if end >= n:
            break
        consumed = 0
        new_start = start
        while new_start < end and consumed < step:
            consumed += len(words[new_start]) + 1
            new_start += 1
        start = new_start if new_start > start else start + 1
    return out


def chunk_markdown(
    text: str,
    *,
    max_chars: int = DEFAULT_MD_MAX_CHARS,
    overlap_chars: int = DEFAULT_MD_OVERLAP_CHARS,
) -> list[str]:
    """Découpe un Markdown de corpus par TITRES ( secours 800 / 100 ).

    Chaque section ( titre `##` + corps ) devient un chunk si elle tient
    dans `max_chars` ; sinon elle est découpée en fenêtres glissantes de
    `max_chars` avec chevauchement `overlap_chars`. Les blocs de code
    ``` sont atomiques ( via `_split_units` ). Jamais de chunk vide.
    """
    if not text or not text.strip():
        return []
    units = _split_units(text)
    sections: list[list[str]] = []
    current: list[str] = []
    for unit, _is_code, is_heading in units:
        if is_heading and current:
            sections.append(current)
            current = []
        current.append(unit)
    if current:
        sections.append(current)

    chunks: list[str] = []
    for section in sections:
        joined = "\n\n".join(section).strip()
        if not joined:
            continue
        if len(joined) <= max_chars:
            chunks.append(joined)
        else:
            chunks.extend(_window_chars(joined, max_chars, overlap_chars))
    return [c for c in chunks if c.strip()]
