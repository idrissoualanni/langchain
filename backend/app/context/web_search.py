# Web Search structuré V6.5 (§17-§23).
#
# recherche_web ne renvoie PLUS une chaîne concaténée : il
# consomme ce module qui produit un SearchResponse (§3).
#
# Pipeline :
#   1. PLAN (§18) : build_web_query(subject, topic, intent,
#      language, user_query) → requête web précise — pas de
#      recherche inutile (question noise §36 : jamais de
#      recherche pédagogique pour « Quelle heure est-il ? »,
#      le router unknown l'arrête avant).
#   2. APPEL : ollama.Client.web_search (provider EXISTANT,
#      §41 — aucun nouveau provider obligatoire).
#   3. NORMALISATION (§20) : chaque résultat → SearchResult
#      (title/url/snippet/content/source_type="web").
#   4. RANKING (§21) : score composite query coverage + topic
#      match + title match + source quality + content
#      relevance — formule ci-dessous, documentée.
#   5. FILTRE (§22) : top_k (3 par défaut) + seuil.
#   6. STATUS (§23) : found / insufficient / unavailable /
#      error — « found = [] » n'existe plus.
#
# Source quality (§19/§21) : les domaines connus pour leur
# documentation officielle (docs.python.org, w3.org...) reçoivent
# un bonus — liste GÉNÉRIQUE de domaines éditoriaux, pas de
# matière : si le domaine n'est pas connu, aucune pénalité ni
# invention (bonus 0). On ne PRIVILÉGIE que ce qui existe.
import re
import unicodedata

from app.context.query_norm import normalize_query
from app.context.schemas import SearchResponse, SearchResult
from app.config import OLLAMA_API_KEY, OLLAMA_HOST
from app.logging.events import log_event

# Seuil de pertinence web (§22) — plus strict que le knowledge
# local car le web est bruité par nature.
WEB_RELEVANCE_THRESHOLD = 0.15

# Domaines éditoriaux de référence (bonus source quality §19).
# Générique : documentation technique officielle, standards,
# éducation. Aucune matière codée en dur.
_OFFICIAL_DOMAINS = {
    "docs.python.org": 1.0,
    "www.python.org": 1.0,
    "developer.mozilla.org": 0.9,
    "www.w3.org": 0.9,
    "tools.ietf.org": 0.9,
    "datatracker.ietf.org": 0.9,
    "fr.wikipedia.org": 0.7,
    "en.wikipedia.org": 0.7,
    "openclassrooms.com": 0.6,
    "fr.khanacademy.org": 0.6,
    "www.khanacademy.org": 0.6,
}

# ==================================================================
# FORMULE DE RANKING WEB V6.5 (§21/§42-C) — documentée + testée.
#
#   web_relevance = 0.35 * coverage_score   (tokens requête web
#                                          couverts par titre+snippet)
#                 + 0.20 * title_score     (tokens dans le titre)
#                 + 0.15 * topic_score     (topic du routing matche)
#                 + 0.20 * source_quality  (domaine officiel §19)
#                 + 0.10 * content_score   (tokens dans le contenu)
#
# Le coverage domine (0.35) : un résultat qui ne parle pas du
# sujet cherché est inutile même sur un site officiel. La
# source quality (0.20) départage à coverage égal. Aucune
# mécanique opaque ; §34 teste pertinent > non pertinent.
# ==================================================================
W_W_COVERAGE = 0.35
W_W_TITLE = 0.20
W_W_TOPIC = 0.15
W_W_SOURCE = 0.20
W_W_CONTENT = 0.10

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_WEB_STOP = {
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "en",
    "d", "l", "the", "a", "of", "and", "in", "is", "are", "for",
    "what", "how", "why", "with", "sur", "pour", "comment", "est",
}


def _strip_accents(text: str) -> str:
    return "".join(
        ch
        for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )


def _tokens(text: str) -> set[str]:
    raw = _TOKEN_RE.findall(_strip_accents((text or "").lower()))
    return {w for w in raw if w not in _WEB_STOP and len(w) >= 3}


def _domain_of(url: str) -> str:
    """Domaine d'une URL (sans www pour matcher la table ? NON :
    la table contient les préfixes tels qu'usuels)."""
    try:
        m = re.match(r"https?://([^/]+)/", url + "/")
        return (m.group(1) if m else "").lower()
    except Exception:
        return ""


def source_quality(url: str) -> float:
    """Bonus domaine éditorial connu (§19) — 0 si inconnu.
    On ne fabrique JAMAIS une source officielle : si le domaine
    n'est pas dans la table, il reste neutre (0.0)."""
    d = _domain_of(url)
    if not d:
        return 0.0
    if d in _OFFICIAL_DOMAINS:
        return _OFFICIAL_DOMAINS[d]
    # préfixe www retiré pour second essai
    d2 = d[4:] if d.startswith("www.") else "www." + d
    return _OFFICIAL_DOMAINS.get(d2, 0.0)


def build_web_query(
    user_query: str,
    subject: str | None = None,
    topic: str | None = None,
    language: str = "fr",
) -> str:
    """PLAN de requête web (§18) : précise la requête user avec
    le contexte disponible (subject, topic, langue).

    « je comprends pas les closures » + python + functions →
    « Python closures functions official documentation » :
      - matière en tête (discriminant fort) ;
      - requête user normalisée (mots signifiants) ;
      - topic si présent ;
      - suffixe « official documentation » si langue FR
        (l'utilisateur FR bénéficie des docs canoniques EN —
        l'anglais domine la doc technique).

    Reste générique : aucune matière codée en dur, le subject
    vient du routing.
    """
    norm = normalize_query(user_query)
    toks = [
        t
        for t in norm.split()
        if t not in _WEB_STOP and len(t) >= 3
    ]
    parts: list[str] = []
    if subject:
        parts.append(subject.replace("_", " "))
    parts.extend(toks[:6])
    if topic and topic not in toks:
        parts.append(topic)
    q = " ".join(parts)
    if language.lower().startswith("fr"):
        q += " official documentation"
    return q


def rank_web_results(
    results: list[dict],
    web_query: str,
    topic: str | None = None,
    top_k: int = 3,
) -> list[SearchResult]:
    """Normalise (§20) + classe (§21) + filtre (§22) les
    résultats bruts ollama → SearchResults triés.

    Entrée : [{title, url, content}, ...] bruts.
    Sortie : SearchResults pertinents, top_k max.
    """
    q_tokens = _tokens(web_query)
    topic_tokens = _tokens(topic or "")
    ranked: list[SearchResult] = []
    for r in results:
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        content = (r.get("content") or "").strip()
        if not url or not title:
            continue
        t_title = _tokens(title)
        t_content = _tokens(content[:500])

        coverage = (
            len(q_tokens & (t_title | t_content)) / len(q_tokens)
            if q_tokens
            else 0.0
        )
        title_s = (
            len(q_tokens & t_title) / len(q_tokens)
            if q_tokens
            else 0.0
        )
        topic_s = (
            len(topic_tokens & (t_title | t_content))
            / len(topic_tokens)
            if topic_tokens
            else 0.0
        )
        source_s = source_quality(url)
        content_s = (
            len(q_tokens & t_content) / len(q_tokens)
            if q_tokens
            else 0.0
        )
        rel = (
            W_W_COVERAGE * coverage
            + W_W_TITLE * title_s
            + W_W_TOPIC * topic_s
            + W_W_SOURCE * source_s
            + W_W_CONTENT * content_s
        )
        ranked.append(
            SearchResult(
                title=title,
                source=_domain_of(url) or url,
                url=url,
                content=content[:1500],
                snippet=content[:280] if content else None,
                relevance=round(min(1.0, rel), 2),
                source_type="web",
                metadata={"source_quality": source_s},
            )
        )
    ranked.sort(key=lambda x: x.relevance, reverse=True)
    return [
        r
        for r in ranked[:top_k]
        if r.relevance >= WEB_RELEVANCE_THRESHOLD
    ]


def web_search(
    user_query: str,
    subject: str | None = None,
    topic: str | None = None,
    language: str = "fr",
    top_k: int = 3,
    user_id: str = "",
    thread_id: str = "",
) -> SearchResponse:
    """Recherche web complète V6.5 → SearchResponse (§3/§17).

    Status (§23) :
      unavailable → OLLAMA_API_KEY absente / client KO
      error       → exception pendant la recherche
      insufficient→ résultats mais aucun ≥ seuil
      found       → ≥1 résultat pertinent
    """
    web_query = build_web_query(
        user_query, subject=subject, topic=topic, language=language
    )
    log_event(
        "WEB_SEARCH_START",
        message=(
            f"Web search start | query={web_query[:80]} | "
            f"subject={subject} | topic={topic}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        extra={
            "operation": "web_search",
            "query": web_query[:100],
            "subject": subject or "",
            "topic": topic or "",
        },
    )

    if not OLLAMA_API_KEY:
        log_event(
            "WEB_SEARCH_UNAVAILABLE",
            level="WARNING",
            message=(
                "Web search unavailable | cause=OLLAMA_API_KEY "
                "absente"
            ),
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "operation": "web_search",
                "status": "unavailable",
                "query": web_query[:100],
            },
        )
        return SearchResponse(
            status="unavailable", query=web_query, results=[]
        )

    try:
        import ollama

        client = ollama.Client(
            host=OLLAMA_HOST,
            headers={"Authorization": f"Bearer {OLLAMA_API_KEY}"},
        )
        raw = client.web_search(
            query=web_query, max_results=max(10, top_k * 3)
        )
        raw_results = [
            {
                "title": getattr(r, "title", "") or "",
                "url": getattr(r, "url", "") or "",
                "content": getattr(r, "content", "") or "",
            }
            for r in (raw.results or [])
        ]
    except Exception as exc:
        # §25 : l'agent CONTINUE — General Tutor fallback
        log_event(
            "WEB_SEARCH_ERROR",
            level="ERROR",
            message=f"Web search error | cause={exc}",
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "operation": "web_search",
                "status": "error",
                "query": web_query[:100],
                "error": str(exc)[:200],
            },
        )
        return SearchResponse(
            status="error", query=web_query, results=[]
        )

    results = rank_web_results(
        raw_results, web_query, topic=topic, top_k=top_k
    )

    # ---- SCRAPING (§26-§34 : chaîne Search → Scrape → Extract →
    # Clean — RUPTURE R8 corrigée). On enrichit le contenu des
    # URLs retenues par le contenu éditorial de la page (le snippet
    # provider reste en secours en cas d'échec partiel §32).
    # Scraping borné : max_scrape = nombre de résultats retenus.
    if results:
        from app.context.web_scraper import scrape_results_snapshot

        scrape_results_snapshot(
            results,
            max_scrape=len(results),
            user_id=user_id,
            thread_id=thread_id,
        )

    status = "found" if results else "insufficient"

    log_event(
        "WEB_SEARCH_END",
        message=(
            f"Web search end | query={web_query[:80]} | "
            f"status={status} | results={len(results)}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        extra={
            "operation": "web_search",
            "query": web_query[:100],
            "subject": subject or "",
            "topic": topic or "",
            "status": status,
            "result_count": len(results),
            "best_relevance": (
                results[0].relevance if results else None
            ),
        },
    )
    return SearchResponse(
        status=status, query=web_query, results=results
    )
