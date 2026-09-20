# Knowledge Retriever — QUOI enseigner (le config dit COMMENT).
# search_knowledge(subject_id, topic, query) → sections pertinentes seulement.
# NE PAS charger tous les documents d'une matière (§7-§9 du brief).
import re
import unicodedata
from pathlib import Path

from app.context.query_norm import (
    normalize_query,
    normalize_tokens,
    variant_forms,
)
from app.context.schemas import SearchResult
from app.logging.events import log_event
from app.subjects.registry import get_subject

# FIX REVUE : knowledge vit dans backend/app/knowledge, ce fichier dans
# backend/app/context/ → parents[0]=context, parents[1]=app
KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge"

# Status possibles (§16) : found / insufficient / unavailable
# (+ "error" transporté par SearchResponse V6.5)
STATUS_FOUND = "found"
STATUS_INSUFFICIENT = "insufficient"
STATUS_UNAVAILABLE = "unavailable"
STATUS_ERROR = "error"

# Seuil de pertinence (fix revue : 0.3, pas 0.15)
RELEVANCE_THRESHOLD = 0.3

# ==================================================================
# FORMULE DE PERTINENCE V6.5 (§6/§42-C) — documentée + testée.
#
#   relevance = 0.30 * topic_score
#             + 0.25 * title_score
#             + 0.20 * phrase_score
#             + 0.15 * content_score
#             + 0.10 * subject_score
#
#   topic_score   ∈ [0,1] : le topic demandé (ou une variante
#                  morphologique, §8) matche le nom de section —
#                  1.0 si exact, 0.5 si variante, sinon 0.
#   title_score   ∈ [0,1] : tokens de la requête couverts par le
#                  titre H1 du fichier de la section.
#   phrase_score  ∈ [0,1] : requête normalisée entière (ou une
#                  sous-phrase ≥2 mots significatifs) contenue
#                  dans la section.
#   content_score ∈ [0,1] : couverture des tokens signifiants de
#                  la requête par le contenu de la section
#                  (containment, stop-words retirés).
#   subject_score∈ {0,1} : le nom de la matière apparaît dans
#                  la requête (contexte explicite).
#
# Pondérations : le topic visé reste dominant (0.30) — une
# section « return » doit sortir avant une section « definition »
# générique pour « c'est quoi return ». Le titre du fichier
# (0.25) départage les sections d'un même fichier. Aucun
# mécanisme opaque ; les tests §34 vérifient pertinent >
# non pertinent.
# ==================================================================
W_TOPIC = 0.30
W_TITLE = 0.25
W_PHRASE = 0.20
W_CONTENT = 0.15
W_SUBJECT = 0.10

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


def _available_sources(subject_id: str) -> list[tuple[Path, str, str]]:
    """Fichiers knowledge réels d'une matière (sources déclarées + présentes).

    V6.5 : retour [(path, source_label, h1_title)] — le titre H1
    extrait UNE fois alimente title_score (§42-C).
    """
    cfg = get_subject(subject_id)
    if cfg is None:
        return []
    files = []
    for src in cfg.knowledge.get("sources", []):
        p = KNOWLEDGE_DIR / f"{src}.md"
        if not p.exists():
            continue
        try:
            content = p.read_text(encoding="utf-8")
        except Exception:
            continue
        h1 = ""
        for line in content.splitlines():
            if line.startswith("# "):
                h1 = line[2:].strip()
                break
        files.append((p, f"{p.parent.name}/{p.stem}", h1))
    return files


# ------------------------------------------------------------------
# Composantes de la formule §42-C — pures et testables
# ------------------------------------------------------------------


def _topic_score(topic: str | None, sec_topic: str) -> float:
    """Score topic (§42-C) : exact 1.0 / variante 0.5 / 0.

    Variantes morphologiques (pluriel/singulier, §8) :
    « fonction » user ≈ « fonctions » section.
    """
    if not topic:
        return 0.0
    t = _strip_accents(topic.lower()).strip()
    s = _strip_accents(sec_topic.lower()).strip()
    if not t or not s:
        return 0.0
    if t == s:
        return 1.0
    if t in variant_forms(s) or s in variant_forms(t):
        return 0.5
    return 0.0


def _title_score(query_tokens: set[str], h1: str) -> float:
    """Score titre (§42-C) : couverture des tokens requête par le H1."""
    if not query_tokens or not h1:
        return 0.0
    title_tokens = _tokens(h1)
    if not title_tokens:
        return 0.0
    return len(query_tokens & title_tokens) / len(query_tokens)


def _phrase_score(query_norm: str, sec_content: str) -> float:
    """Score phrase (§42-C) : requête entière, ou sous-phrase
    significative (≥2 tokens), contenue dans la section."""
    if not query_norm:
        return 0.0
    sec_norm = normalize_query(sec_content)
    if query_norm in sec_norm:
        return 1.0
    toks = normalize_tokens(query_norm)
    sig = [
        t
        for t in toks
        if t not in _KN_STOP_WORDS and len(t) >= 3
    ]
    for size in range(len(sig) - 1, 1, -1):
        for i in range(len(sig) - size + 1):
            sub = " ".join(sig[i : i + size])
            if sub and sub in sec_norm:
                return min(1.0, 0.4 + 0.15 * size)
    return 0.0


def _content_score(
    query_tokens: set[str], sec_tokens: set[str]
) -> float:
    """Score contenu (§42-C) : containment tokens requête."""
    if not query_tokens or not sec_tokens:
        return 0.0
    return len(query_tokens & sec_tokens) / len(query_tokens)


def _subject_score(query: str, subject_id: str) -> float:
    """Score matière (§42-C) : matière ou alias explicite dans
    la requête — réutilise SubjectConfig.aliases (§9), aucune
    seconde liste."""
    if not query or not subject_id:
        return 0.0
    qn = normalize_query(query)
    if subject_id.lower() in qn:
        return 1.0
    cfg = get_subject(subject_id)
    if cfg:
        for alias in cfg.aliases:
            if normalize_query(alias) in qn:
                return 1.0
    return 0.0


def score_section(
    subject_id: str,
    topic: str | None,
    query: str,
    query_norm: str,
    query_tokens: set[str],
    sec_topic: str,
    sec_content: str,
    sec_title: str,
) -> float:
    """Formule composite §42-C — pure et testable.

    Cf. bloc documentation en tête de module. Plafonnée à 1.0,
    arrondie à 2 décimales.
    """
    t = _topic_score(topic, sec_topic)
    ti = _title_score(query_tokens, sec_title)
    p = _phrase_score(query_norm, sec_content)
    c = _content_score(query_tokens, _tokens(sec_content[:600]))
    s = _subject_score(query, subject_id)
    score = (
        W_TOPIC * t
        + W_TITLE * ti
        + W_PHRASE * p
        + W_CONTENT * c
        + W_SUBJECT * s
    )
    return round(min(1.0, score), 2)


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
    """Recherche les sections knowledge pertinentes (V6.5).

    Pipeline §4 : normalisation (§8) → sources autorisées →
    scoring composite §42-C → tri → seuil RELEVANCE_THRESHOLD
    → top_k (limit).

    Retourne un dict SearchResponse-compatible :
    {
        "status": found|insufficient|unavailable,
        "query": <requête normalisée>,
        "results": [SearchResult.model_dump()...],
        "items": [compat V5 builder],
        "searched_sources": int,
    }
    """
    q_norm = normalize_query(query or (topic or ""))
    query_tokens = _tokens(query or (topic or ""))

    items: list[SearchResult] = []

    sources = _available_sources(subject_id)

    if query_tokens:
        for path, source_label, h1 in sources:
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue
            for sec_topic, sec_content in _split_sections(content):
                if not sec_content:
                    continue
                rel = score_section(
                    subject_id=subject_id,
                    topic=topic,
                    query=query or (topic or ""),
                    query_norm=q_norm,
                    query_tokens=query_tokens,
                    sec_topic=sec_topic,
                    sec_content=sec_content,
                    sec_title=h1,
                )
                if rel >= RELEVANCE_THRESHOLD:
                    items.append(
                        SearchResult(
                            title=h1 or source_label,
                            source=source_label,
                            content=sec_content,
                            relevance=rel,
                            source_type="local_knowledge",
                            metadata={"section": sec_topic},
                        )
                    )

    items.sort(key=lambda r: r.relevance, reverse=True)
    items = items[:limit]

    if not sources:
        status = STATUS_UNAVAILABLE
    elif items:
        status = STATUS_FOUND
    else:
        status = STATUS_INSUFFICIENT

    # Compat V5 : vue items pour le builder
    legacy_items = [
        {
            "source": r.source,
            "topic": r.metadata.get("section", ""),
            "content": r.content,
            "relevance": r.relevance,
        }
        for r in items
    ]

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
        "query": q_norm,
        "results": [r.model_dump() for r in items],
        "items": legacy_items,
        "searched_sources": len(sources),
    }
