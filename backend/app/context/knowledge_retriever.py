# Knowledge Retriever — QUOI enseigner (le config dit COMMENT).
# search_knowledge(subject_id, topic, query) → sections pertinentes seulement.
# NE PAS charger tous les documents d'une matière (§7-§9 du brief).
import re
import unicodedata
from pathlib import Path

from app.logging.events import log_event
from app.subjects.registry import get_subject

# FIX REVUE : knowledge vit dans backend/app/knowledge, ce fichier dans
# backend/app/context/ → parents[0]=context, parents[1]=app
KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"

# Status possibles (§16) : found / insufficient / unavailable
STATUS_FOUND = "found"
STATUS_INSUFFICIENT = "insufficient"
STATUS_UNAVAILABLE = "unavailable"

# Seuil de pertinence (fix revue : 0.3, pas 0.15)
RELEVANCE_THRESHOLD = 0.3

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Stop-words français/anglais retirés des tokens requête (fix revue)
_KN_STOP_WORDS = {
    "le", "la", "les", "un", "une", "des", "de", "du", "d", "l",
    "et", "ou", "en", "y", "a", "au", "aux", "avec", "sans", "dans",
    "pour", "par", "sur", "est", "sont", "suis", "es", "etre", "je",
    "tu", "il", "elle", "on", "nous", "vous", "ils", "elles", "me",
    "moi", "ma", "mon", "mes", "te", "toi", "ta", "ton", "tes", "sa",
    "son", "ses", "que", "qui", "quoi", "ce", "cet", "cette", "ces",
    "explique", "expliquer", "expliques", "moi", "comment", "pourquoi",
    "quelle", "quel", "quelles", "quels", "fonctionne", "marche",
    "the", "is", "are", "in", "of", "and", "me", "my", "what", "how",
    "python",  # le nom de la matière est déjà le contexte, pas un discriminateur
}


def _strip_accents(text: str) -> str:
    """Normalise accents (NFD fold) — matching FR indépendant des accents."""
    return "".join(
        ch
        for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )


def _tokens(text: str) -> set[str]:
    """Tokens normalisés : minuscules, sans accents, sans stop-words."""
    raw = _TOKEN_RE.findall(_strip_accents((text or "").lower()))
    return {w for w in raw if w not in _KN_STOP_WORDS}


def _available_sources(subject_id: str) -> list[Path]:
    """Fichiers knowledge réels d'une matière (sources déclarées + présentes)."""
    cfg = get_subject(subject_id)
    if cfg is None:
        return []
    files = []
    for src in cfg.knowledge.get("sources", []):
        p = KNOWLEDGE_DIR / f"{src}.md"
        if p.exists():
            files.append(p)
    return files


def resolve_topic_source(
    subject_id: str, topic: str
) -> tuple[str, str] | None:
    """PONT Registry ↔ knowledge (mission intégration §10) :

    Résout un topic REGISTRY (ex: « fonctions ») vers son fichier
    knowledge réel (ex: informatique/python/functions → « Fonctions »).
    Stratégie, dans l'ordre, SANS hardcoding de matière :
      1. stem exact du fichier (functions → functions.md) ;
      2. topic normalisé contenu dans le titre H1 du fichier
         (« fonctions » ⊂ « Python — Fonctions »).
    Retour (source_yaml, section_de_départ) ou None — jamais
    inventé. Utilisé par les tools pédagogiques pour faire le pont
    entre les topics du Registry (routing V4) et les sections
    réelles des fichiers knowledge.
    """
    cfg = get_subject(subject_id)
    if cfg is None or not topic:
        return None
    norm = _strip_accents(topic.lower())
    for src in cfg.knowledge.get("sources", []):
        p = KNOWLEDGE_DIR / f"{src}.md"
        if not p.exists():
            continue
        try:
            content = p.read_text(encoding="utf-8")
        except Exception:
            continue
        # 1. stem exact
        stem = src.rsplit("/", 1)[-1]
        if _strip_accents(stem.lower()) == norm:
            return src, stem
        # 2. token du titre H1
        for line in content.splitlines():
            if line.startswith("# "):
                if norm in _strip_accents(line[2:].lower()):
                    return src, stem
                break
    return None


def _split_sections(content: str) -> list[tuple[str, str]]:
    """Découpe un .md en sections (## topic). Retour [(topic, contenu)]."""
    sections = []
    current_topic = "_intro"
    current_lines: list[str] = []
    for line in content.splitlines():
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            if current_lines:
                sections.append(
                    (current_topic, "\n".join(current_lines).strip())
                )
            current_topic = _strip_accents(
                m.group(1).strip().lower()
            )
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append(
            (current_topic, "\n".join(current_lines).strip())
        )
    return sections


def search_knowledge(
    subject_id: str,
    topic: str | None = None,
    query: str = "",
    limit: int = 3,
) -> dict:
    """Recherche les sections knowledge pertinentes.

    Retourne :
    {
        "status": found|insufficient|unavailable,
        "items": [{"source", "topic", "content", "relevance"}],
        "searched_sources": int,
    }

    Scoring (fix revue) : tokens signifiants uniquement (stop-words
    retirés), ≥1 token signifiant requis dans la requête, seuil 0.3.
    """
    query_tokens = _tokens(query or (topic or ""))
    items: list[dict] = []

    sources = _available_sources(subject_id)

    if query_tokens:
        for path in sources:
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue
            source_label = f"{path.parent.name}/{path.stem}"
            for sec_topic, sec_content in _split_sections(content):
                if not sec_content:
                    continue
                section_tokens = _tokens(
                    f"{sec_topic} {sec_content[:400]}"
                )
                if not section_tokens:
                    continue
                # Containment : tokens requête présents dans la section
                overlap = (
                    len(query_tokens & section_tokens)
                    / len(query_tokens)
                )
                # Bonus si le topic demandé correspond au nom de section
                if topic:
                    norm_topic = _strip_accents(topic.lower())
                    if norm_topic in sec_topic or sec_topic in norm_topic:
                        overlap = min(1.0, overlap + 0.5)
                if overlap >= RELEVANCE_THRESHOLD:
                    items.append(
                        {
                            "source": source_label,
                            "topic": sec_topic,
                            "content": sec_content,
                            "relevance": round(overlap, 2),
                        }
                    )

    items.sort(key=lambda x: x["relevance"], reverse=True)
    items = items[:limit]

    if not sources:
        status = STATUS_UNAVAILABLE
    elif items:
        status = STATUS_FOUND
    else:
        status = STATUS_INSUFFICIENT

    log_event(
        "KNOWLEDGE_SEARCH",
        message=(
            f"Knowledge search | subject={subject_id} | "
            f"topic={topic} | status={status} | items={len(items)}"
        ),
        extra={
            "operation": "knowledge_search",
            "subject": subject_id,
            "topic": topic or "",
            "status": status,
            "items": len(items),
        },
    )
    return {
        "status": status,
        "items": items,
        "searched_sources": len(sources),
    }
