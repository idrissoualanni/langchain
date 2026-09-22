# Web Scraper V11 — SCRAPING des URLs retenues par le ranking web.
#
# MISSION FINALE §26-§34 : la chaîne Search → Scrape → Extract →
# Clean était INCOMPLÈTE (R8) : le « content » fourni par
# ollama.web_search est un snippet de recherche (borné, parfois
# vide), PAS le contenu de la page. Ce module complète la chaîne :
#
#   fetch_page_content(url) → texte de la page (HTML nettoyé) ou None
#
# Règles (mission V11) :
#   - ÉCHEC CONTROLÉ : HTTP status ≠ 200, timeout, non-HTML,
#     exception → retour None (jamais d'exception propagée).
#   - EXTRACTION propre : strip script/style/nav/header/footer/
#     aside/forms/iframes/noscript — le « contenu éditorial » seul.
#   - BORNE : MAX_SCRAPE_CHARS par page (budget tokens du prompt).
#   - ÉCHEC PARTIEL (§32) : l'appelant IGNORE une URL en échec et
#     conserve le snippet provider — jamais d'échec global.
#
# Aucun nouveau framework d'inférence : requests (déjà présent) +
# BeautifulSoup (déjà présent) — rien de nouveau à installer.
from __future__ import annotations

import logging

import requests
from bs4 import BeautifulSoup

from app.logging.events import log_event

logger = logging.getLogger("web_scraper")

# Timeout par page (mission §29 : ne jamais geler le chat).
SCRAPE_TIMEOUT_S = 8.0

# Borne du contenu éditorial extrait (une page ≠ les 10 pages).
MAX_SCRAPE_CHARS = 6000

# Statuts observables (events SCRAPE_* §33) :
#   scraped    → contenu extrait et remplacé
#   unchanged  → échec/refus → snippet provider conservé
SCRAPE_STATUS = ("scraped", "unchanged")

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Balises purement structurelles / publicitaires / interactives,
# jamais du contenu éditorial.
_STRIP_TAGS = [
    "script", "style", "nav", "header", "footer", "aside",
    "form", "iframe", "noscript", "template", "svg", "button",
    "figcaption",
]


def _clean_text(html: str) -> str:
    """Extrait le texte éditorial d'une page HTML, nettoyé."""
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return ""
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [
        (line.strip() or "").strip("\u00a0")
        for line in text.splitlines()
    ]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def fetch_page_content(
    url: str,
    *,
    user_id: str = "",
    thread_id: str = "",
    timeout_s: float = SCRAPE_TIMEOUT_S,
    max_chars: int = MAX_SCRAPE_CHARS,
) -> tuple[str, str | None]:
    """Télécharge et extrait le contenu éditorial d'UNE page.

    Retour : (statut, contenu) où
      ("scraped", texte)   → extraction réussie ;
      ("unchanged", None)  → échec contrôlé / contenu non-HTML /
                             à nouveau d'aucune utilité.

    FAIL-SAFE (mission V11 §29) : aucune exception ne sort de
    cette fonction — un site qui résiste ne doit JAMAIS casser
    le chat ni la recherche web.
    """
    log_event(
        "SCRAPE_START",
        message=f"Scrape start | url={url[:120]}",
        user_id=user_id,
        thread_id=thread_id,
        extra={"operation": "web_scrape", "url": url[:200]},
    )
    try:
        resp = requests.get(
            url,
            timeout=timeout_s,
            allow_redirects=True,
            headers={
                "User-Agent": _DEFAULT_UA,
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                "Accept-Language": "fr,fr-FR;q=0.9,en;q=0.8",
            },
        )
        if resp.status_code != 200:
            log_event(
                "SCRAPE_ERROR",
                level="WARNING",
                message=(
                    f"Scrape error | url={url[:80]} | "
                    f"status={resp.status_code}"
                ),
                user_id=user_id,
                thread_id=thread_id,
                extra={"status_code": resp.status_code},
            )
            return ("unchanged", None)

        ctype = (resp.headers.get("Content-Type") or "").lower()
        if "html" not in ctype and "text/" not in ctype:
            # PDF, octet-stream, images… : pas de scraping texte fiable
            # ici — snippet provider conservé (échec partiel ±32).
            log_event(
                "SCRAPE_SKIP",
                level="INFO",
                message=(
                    f"Scrape skip (non HTML) | url={url[:80]} | "
                    f"ctype={ctype[:40]}"
                ),
                user_id=user_id,
                thread_id=thread_id,
                extra={"content_type": ctype[:60]},
            )
            return ("unchanged", None)

        text = _clean_text(resp.text)
        text = text[:max_chars]
        if len(text.strip()) < 80:
            log_event(
                "SCRAPE_SKIP",
                level="INFO",
                message=(
                    f"Scrape skip (contenu vide) | url={url[:80]}"
                ),
                user_id=user_id,
                thread_id=thread_id,
            )
            return ("unchanged", None)

        log_event(
            "SCRAPE_END",
            message=(
                f"Scrape end | url={url[:80]} | chars={len(text)}"
            ),
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "operation": "web_scrape",
                "url": url[:200],
                "chars": len(text),
            },
        )
        return ("scraped", text)

    except requests.exceptions.Timeout:
        log_event(
            "SCRAPE_ERROR",
            level="WARNING",
            message=f"Scrape error (timeout) | url={url[:80]}",
            user_id=user_id,
            thread_id=thread_id,
            extra={"cause": "timeout"},
        )
        return ("unchanged", None)
    except requests.exceptions.SSLError as exc:
        log_event(
            "SCRAPE_ERROR",
            level="WARNING",
            message=(
                f"Scrape error (ssl) | url={url[:80]} | cause={str(exc)[:120]}"
            ),
            user_id=user_id,
            thread_id=thread_id,
            extra={"cause": "ssl"},
        )
        return ("unchanged", None)
    except requests.exceptions.RequestException as exc:
        log_event(
            "SCRAPE_ERROR",
            level="WARNING",
            message=(
                f"Scrape error | url={url[:80]} | cause={str(exc)[:120]}"
            ),
            user_id=user_id,
            thread_id=thread_id,
            extra={"cause": str(exc)[:160]},
        )
        return ("unchanged", None)
    except Exception as exc:  # pragma: no cover — défensif
        logger.error("Scrape échec inattendu %s: %s", url[:80], exc)
        log_event(
            "SCRAPE_ERROR",
            level="ERROR",
            message=f"Scrape error (unexpected) | url={url[:80]}",
            user_id=user_id,
            thread_id=thread_id,
            extra={"cause": str(exc)[:160]},
        )
        return ("unchanged", None)


def scrape_results_snapshot(
    results,
    *,
    max_scrape: int = 3,
    user_id: str = "",
    thread_id: str = "",
) -> list:
    """Enrichit les SearchResults par leur contenu de page.

    ÉCHEC PARTIEL (§32) : chaque URL est tentée indépendamment.
    Une URL bloquée/injoignable garde son snippet provider — les
    autres pages sont tout de même scrapées. Ne touche JAMAIS à
    la pertinence (le ranking est déjà fait, logiciel existant).

    Retourne la liste (les objets SearchResult peuvent être
    mutés en place pour simplicité — ils sont présontés par
    copie de l'appelant).
    """
    scraped_results: list = []
    for r in results[:max_scrape]:
        url = (r.url or "").strip() if hasattr(r, "url") else ""
        if not url:
            scraped_results.append(r)
            continue
        status, text = fetch_page_content(
            url, user_id=user_id, thread_id=thread_id
        )
        if status == "scraped" and text:
            r.content = text
            r.snippet = (text[:280] + ("…" if len(text) > 280 else ""))
            if isinstance(getattr(r, "metadata", None), dict):
                r.metadata["scraped"] = "yes"
        scraped_results.append(r)
    return scraped_results


__all__ = [
    "SCRAPE_STATUS",
    "SCRAPE_TIMEOUT_S",
    "MAX_SCRAPE_CHARS",
    "fetch_page_content",
    "scrape_results_snapshot",
]