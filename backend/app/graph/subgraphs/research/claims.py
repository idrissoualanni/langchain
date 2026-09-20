# Research Subgraph — EXTRACTION de claims, VÉRIFICATION/comparaison
# de sources et SYNTHÈSE (V1, DÉTERMINISTE, aucun LLM).
#
# Sécurité (prompt injection) :
#   - le contenu web est traité comme DONNÉES NON FIABLES — jamais
#     comme instructions : aucune exécution, aucune injection dans un
#     prompt système ; la synthèse ne fait que CITer des extraits ;
#   - des marqueurs d'injection/commandes (blocs de code, "import ",
#     "exec(", "system(", fences markdown, shebang) font REJETER la
#     phrase du corpus de claims.
from __future__ import annotations

import re
import unicodedata

MAX_CLAIMS_PER_SOURCE = 3
MAX_TOTAL_CLAIMS = 12
MIN_CLAIM_LEN = 40
MAX_CLAIM_LEN = 340

_SENT_RE = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"[a-z0-9]{4,}")
_NUM_RE = re.compile(r"\b\d+(?:[.,]\d+)?\b")

# Marqueurs de négation (polarité d'un énoncé).
_NEGATION_RE = re.compile(r"\b(ne|pas|jamais|aucun|aucune|sans|non|rien)\b")

# Marqueurs d'injection / contenu non éditorial (données → rejet SANS
# interprétation : on traite la source comme donnée, pas comme code).
_INJECTION_MARKERS = (
    "```",
    "#!/",
    "import ",
    "from ",
    "exec(",
    "eval(",
    "system(",
    "subprocess",
    "os.system",
    "; rm ",
    "`rm ",
    "<script",
)

_STOP = {
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "en",
    "au", "aux", "d", "l", "the", "a", "an", "of", "and", "in", "is",
    "are", "pour", "quoi", "comment", "est", "que", "qui", "ce", "c",
    "je", "tu", "il", "elle", "nous", "vous", "sur", "avec", "dans",
    "par", "moi", "toi", "plus", "cette", "ces", "cet", "tout", "tres",
}


def _strip_accents(text: str) -> str:
    return "".join(
        ch
        for ch in unicodedata.normalize("NFD", text or "")
        if unicodedata.category(ch) != "Mn"
    )


def _normalize(text: str) -> str:
    return _strip_accents((text or "").lower())


def _sig_tokens(text: str) -> list[str]:
    """Tokens signifiants d'un texte (≥ 4 chars, hors stop-words)."""
    norm = _normalize(text)
    return [t for t in _WORD_RE.findall(norm) if t not in _STOP]


def _split_sentences(content: str) -> list[str]:
    text = re.sub(r"\s+", " ", (content or "").replace("\r", " "))
    return [
        s.strip()
        for s in _SENT_RE.split(text)
        if s and s.strip()
    ]


def _is_injection(sentence: str) -> bool:
    low = sentence.lower()
    return any(m in low for m in _INJECTION_MARKERS)


def extract_claims_from_sources(
    sources: list,
    question: str = "",
    max_per_source: int = MAX_CLAIMS_PER_SOURCE,
    max_total: int = MAX_TOTAL_CLAIMS,
) -> list[dict]:
    """Extrait des claims/faits structurés depuis les sources web.

    DÉTERMINISTE :
      - phrases 40..340 chars, sans marqueur d'injection ;
      - priorité aux phrases en recouvrement lexical avec la question ;
      - borné (max_per_source phrases / source, max_total claims) ;
      - dédupliqué (normalisation) ;
      - fallback : si rien ne matche la question, la meilleure phrase
        (par longueur) de chaque source est conservée pour ne pas
        vider le corpus — toujours en tant que DONNÉES.

    Claim : {claim, source, source_title, url, confidence, snippet}.
    """
    q_tokens = set(_sig_tokens(question or ""))

    def _score(sentence: str) -> tuple[int, int]:
        toks = set(_WORD_RE.findall(_normalize(sentence)))
        overlap = len(q_tokens & toks) if q_tokens else 0
        return overlap, len(toks)

    claims: list[dict] = []
    seen: set[str] = set()

    for src in sources:
        src = dict(src or {})
        content = str(src.get("content") or src.get("snippet") or "")
        if not content.strip():
            continue
        sentences = [
            s
            for s in _split_sentences(content)
            if MIN_CLAIM_LEN <= len(s) <= MAX_CLAIM_LEN
            and not _is_injection(s)
        ]
        if not sentences:
            continue
        ranked = sorted(sentences, key=_score, reverse=True)[:max_per_source]
        for sentence in ranked:
            corr = _normalize(sentence)
            if corr in seen:
                continue
            overlap, _ = _score(sentence)
            if q_tokens and overlap == 0:
                continue
            seen.add(corr)
            confidence = round(
                min(
                    0.95,
                    0.45
                    + 0.15 * min(overlap, 3)
                    + 0.05 * min(len(_normalize(sentence)) / 100, 1.0),
                ),
                2,
            )
            url = str(src.get("url") or "") or str(src.get("source") or "")
            claims.append(
                {
                    "claim": sentence,
                    "source": url or "inconnue",
                    "source_title": str(src.get("title") or "")[:120],
                    "url": url or None,
                    "confidence": confidence,
                    "snippet": sentence[:220],
                }
            )
            if len(claims) >= max_total:
                return claims
        if len(claims) >= max_total:
            return claims

    # Fallback borné : aucune phrase pertinente pour la question →
    # on garde la phrase la plus longue de chaque source (données).
    if not claims:
        for src in sources:
            src = dict(src or {})
            content = str(src.get("content") or src.get("snippet") or "")
            candidates = [
                s
                for s in _split_sentences(content)
                if MIN_CLAIM_LEN <= len(s) <= MAX_CLAIM_LEN
                and not _is_injection(s)
            ]
            if not candidates:
                continue
            sentence = max(candidates, key=len)
            url = str(src.get("url") or "") or str(src.get("source") or "")
            claims.append(
                {
                    "claim": sentence,
                    "source": url or "inconnue",
                    "source_title": str(src.get("title") or "")[:120],
                    "url": url or None,
                    "confidence": 0.40,
                    "snippet": sentence[:220],
                }
            )
            if len(claims) >= max_total:
                break
    return claims


def _has_negation(text: str) -> bool:
    return bool(_NEGATION_RE.search(_normalize(text)))


def compare_sources(
    claims: list,
    sources: list | None = None,
) -> dict:
    """Vérifie les claims (corroboration) et compare les sources.

    V1 déterministe :
      - evidence  : par claim {claim_id, claim, source,
                    corroboration, verdict} — "corroborated" si un
                    autre claim partage ≥1 token signifiant, sinon
                    "single_source" ;
      - contradictions : paires de claims au topic partagé avec
                    polarité opposée, ou valeurs numériques
                    divergentes (heuristique bornée) ;
      - findings   : top-5 claims (corroboration, confiance) ;
      - missing_information : limites du cross-check.
    """
    claims = [dict(c) for c in (claims or [])]
    n = len(claims)
    tokens: list[set[str]] = [
        set(_sig_tokens(c.get("claim") or "")) for c in claims
    ]

    evidence: list[dict] = []
    for i in range(n):
        others = [
            j for j in range(n)
            if j != i and (tokens[i] & tokens[j])
        ]
        evidence.append(
            {
                "claim_id": i,
                "claim": claims[i].get("claim", ""),
                "source": claims[i].get("source", ""),
                "corroboration": len(others),
                "verdict": "corroborated" if len(others) >= 1 else "single_source",
            }
        )

    contradictions: list[dict] = []
    for i in range(n):
        for j in range(i + 1, n):
            shared = tokens[i] & tokens[j]
            if not shared:
                continue
            ca = claims[i].get("claim", "")
            cb = claims[j].get("claim", "")
            na = _has_negation(ca)
            nb = _has_negation(cb)
            if na != nb:
                contradictions.append(
                    {
                        "kind": "polarite",
                        "topic": sorted(shared)[0],
                        "claim_a": ca,
                        "claim_b": cb,
                        "source_a": claims[i].get("source", ""),
                        "source_b": claims[j].get("source", ""),
                    }
                )
            elif len(shared) >= 2:
                nums_a = set(_NUM_RE.findall(ca))
                nums_b = set(_NUM_RE.findall(cb))
                if nums_a and nums_b and nums_a != nums_b:
                    contradictions.append(
                        {
                            "kind": "valeur_numerique",
                            "topic": sorted(shared)[0],
                            "claim_a": ca,
                            "claim_b": cb,
                            "source_a": claims[i].get("source", ""),
                            "source_b": claims[j].get("source", ""),
                        }
                    )

    findings = sorted(
        [
            {
                "claim": e["claim"],
                "source": e["source"],
                "confidence": float(
                    claims[e["claim_id"]].get("confidence", 0.0) or 0.0
                ),
                "corroboration": e["corroboration"],
                "verdict": e["verdict"],
            }
            for e in evidence
        ],
        key=lambda f: (f["corroboration"], f["confidence"]),
        reverse=True,
    )[:5]

    missing_information: list[str] = []
    if not claims:
        missing_information.append(
            "Aucun fait exploitable extrait des sources consultées."
        )
    single = sum(1 for e in evidence if e["verdict"] == "single_source")
    if single:
        missing_information.append(
            f"Cross-check limité : {single} fait(s) reposent sur une seule source."
        )

    return {
        "evidence": evidence,
        "contradictions": contradictions,
        "findings": findings,
        "missing_information": missing_information,
    }


def synthesize_report(
    question: str,
    objective: str,
    plan_queries: list,
    sources: list,
    claims: list,
    evidence: list,
    findings: list,
    contradictions: list,
    missing_information: list,
    errors: list,
    iteration: int,
    max_iterations: int,
) -> tuple[dict, str]:
    """Construit le rapport structuré + le résumé lisible (V1).

    La synthèse ne fait que CITER des extraits sourcés — aucune
    instruction des sources n'est interprétée.
    """
    report = {
        "question": question,
        "objective": objective,
        "plan": [str(q or "") for q in (plan_queries or [])],
        "sources": [
            {
                "title": str(s.get("title") or "")[:120],
                "url": s.get("url"),
                "source": str(s.get("source") or ""),
                "relevance": float(s.get("relevance", 0.0) or 0.0),
            }
            for s in (sources or [])
        ],
        "claims": [dict(c) for c in (claims or [])],
        "evidence": [dict(e) for e in (evidence or [])],
        "findings": [dict(f) for f in (findings or [])],
        "contradictions": [dict(x) for x in (contradictions or [])],
        "missing_information": [
            str(m) for m in (missing_information or []) if m
        ],
        "errors": [dict(e) for e in (errors or [])],
        "iteration": int(iteration or 0),
        "max_iterations": int(max_iterations or 0),
    }

    lines: list[str] = []
    src_count = len(sources or [])
    lines.append(
        f"Recherche menée sur {src_count} source(s) pour la question : "
        f"{question or '(vide)'}."
    )
    if findings:
        lines.append("Faits principaux :")
        for i, f in enumerate(findings, 1):
            src = str(f.get("source") or "").strip()
            lines.append(f"  {i}. {f.get('claim', '')} [source: {src or 'inconnue'}]")
    if contradictions:
        lines.append(
            f"Contradictions détectées : {len(contradictions)} entre sources."
        )
    if missing_information:
        lines.append(
            "Limites : "
            + " ; ".join(str(m) for m in missing_information if m)
        )
    if errors:
        lines.append(f"Erreurs techniques : {len(errors)} (voir le rapport).")
    if not findings:
        lines.append("Aucun fait exploitable extrait — synthèse non concluante.")
    return report, "\n".join(lines)


__all__ = [
    "extract_claims_from_sources",
    "compare_sources",
    "synthesize_report",
    "MAX_CLAIMS_PER_SOURCE",
    "MAX_TOTAL_CLAIMS",
]