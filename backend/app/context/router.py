# Subject Router — détecte (subject, topic, confidence, status) d'une question.
# Déterministe : scoring de mots-clés sur aliases + topics des SubjectConfig.
# Statuts (§13) : supported / ambiguous / unsupported / unknown / multi_domain
#
# Fallbacks = situations NORMALES (§34), jamais des erreurs :
#   supported   → matière configurée, contexte spécialisé construit
#   ambiguous   → plusieurs interprétations → clarification demandée
#   unsupported → matière détectée mais non configurée → tuteur général
#   unknown     → rien d'identifié → tuteur général
#   multi_domain→ plusieurs domaines évoqués (identification V4, §32)
import re
import unicodedata
from dataclasses import dataclass, field

from app.logging.events import log_event
from app.subjects.registry import get_subject, list_subjects
from app.subjects.taxonomy import active_taxonomy

STATUS_SUPPORTED = "supported"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_UNSUPPORTED = "unsupported"
STATUS_UNKNOWN = "unknown"
STATUS_MULTI_DOMAIN = "multi_domain"

CONFIDENCE_SUPPORTED = 0.95   # alias direct + topic identifié
CONFIDENCE_TOPIC = 0.85       # alias direct sans topic
CONFIDENCE_UNSUPPORTED = 0.9  # matière taxonomy détectée non-configurée
CONFIDENCE_LOW = 0.3          # rien d'identifié

_WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass
class RouterResult:
    subject: str | None
    topic: str | None
    confidence: float
    status: str
    candidates: list[str] = field(default_factory=list)
    subjects: list[str] = field(default_factory=list)  # multi_domain
    note: str = ""


def _strip_accents(text: str) -> str:
    """Normalise accents (NFD fold) — matching indépendant des accents."""
    return "".join(
        ch
        for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )


def _norm(text: str) -> str:
    return _strip_accents((text or "").lower()).strip()


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(_norm(text))


def _phrase_in(text_norm: str, phrase: str) -> bool:
    """Alias multi-mots : sous-chaîne normalisée."""
    return _norm(phrase) in text_norm


def _word_in(q_words: set[str], word: str) -> bool:
    """Alias/mot simple : frontière de mots (fix revue §15 — 'py' dans
    'manipulation' ne doit pas matcher)."""
    return _norm(word) in q_words


def _match_topic(cfg, q_words: set[str], text_norm: str) -> str | None:
    """Topic de la config présent dans la question (mot ou phrase)."""
    for topic in cfg.topics:
        t = _norm(topic)
        if " " in t or "/" in t:
            if t in text_norm:
                return topic
        elif t and t in q_words:
            return topic
    return None


def _emit_end(result: RouterResult) -> RouterResult:
    log_event(
        "ROUTING_END",
        message=(
            f"Routed | subject={result.subject} | "
            f"topic={result.topic} | status={result.status} | "
            f"confidence={result.confidence}"
        ),
        extra={
            "operation": "routing",
            "subject": result.subject,
            "topic": result.topic,
            "status": result.status,
            "confidence": result.confidence,
            "candidates": result.candidates,
        },
    )
    return result


def route_subject(
    query: str, hint_subject: str | None = None
) -> RouterResult:
    """Détermine la matière/topic d'une question (déterministe, sans LLM).

    hint_subject : subject transmis explicitement (API preview, futur
    HITL) — s'il est configuré, il l'emporte.
    """
    log_event(
        "ROUTING_START",
        message=f"Routing | query={(query or '')[:80]}",
        extra={"operation": "routing", "query": (query or "")[:100]},
    )

    text_norm = _norm(query or "")
    q_words = set(_words(query or ""))

    # 1) Hint explicite → supported si configuré
    if hint_subject:
        cfg = get_subject(hint_subject)
        if cfg:
            topic = _match_topic(cfg, q_words, text_norm)
            return _emit_end(
                RouterResult(
                    subject=cfg.id,
                    topic=topic,
                    confidence=(
                        CONFIDENCE_SUPPORTED
                        if topic
                        else CONFIDENCE_TOPIC
                    ),
                    status=STATUS_SUPPORTED,
                )
            )

    # 2) Scoring des matières CONFIGURÉES (aliases + topics)
    scores: dict[str, float] = {}
    topic_by_subject: dict[str, str | None] = {}
    for cfg in list_subjects():
        score = 0.0
        # alias — phrases d'abord (les plus longues d'abord)
        for alias in sorted(cfg.aliases, key=len, reverse=True):
            a = _norm(alias)
            if " " in a or "/" in a:
                if _phrase_in(text_norm, alias):
                    score = max(score, 2.0)
            else:
                if _word_in(q_words, alias):
                    score = max(score, 2.0)
        # topic direct
        topic = _match_topic(cfg, q_words, text_norm)
        topic_by_subject[cfg.id] = topic
        if topic:
            score = max(score, 1.0)
        if score > 0:
            scores[cfg.id] = score

    # 3) Détection taxonomy (matières non-configurées)
    #    FIX REVUE : anti-collision sur les HITS, pas sur les ids —
    #    un id configuré ne devient "unsupported" QUE si ses aliases
    #    YAML explicites n'ont pas matché (ex: "reseaux" nu n'est PAS
    #    dans le YAML computer_networks, donc l'entrée taxonomy
    #    computer_networks participe à l'ambiguïté avec neural_networks).
    registry_ids = set(load_registry_ids())
    configured_hit_ids = set(scores.keys())
    unsupported_hits: list[str] = []
    for taxo in active_taxonomy(set()):
        # Une entrée taxonomy dont l'id est configuré ne compte que
        # si le subject configuré n'a PAS été détecté par ses aliases
        if taxo.id in registry_ids and taxo.id in configured_hit_ids:
            continue
        for alias in taxo.aliases:
            a = _norm(alias)
            hit = (
                _phrase_in(text_norm, alias)
                if " " in a
                else _word_in(q_words, alias)
            )
            if hit:
                unsupported_hits.append(taxo.id)
                break

    # 4) Décision
    if scores:
        best_id = max(scores, key=lambda k: scores[k])
        top = scores[best_id]
        values = sorted(scores.values(), reverse=True)
        second = values[1] if len(values) > 1 else 0.0

        # Égalité parfaite au top entre matières configurées → ambiguous
        if len(scores) >= 2 and top == second:
            return _emit_end(
                RouterResult(
                    subject=None,
                    topic=None,
                    confidence=0.5,
                    status=STATUS_AMBIGUOUS,
                    candidates=sorted(scores.keys()),
                )
            )

        topic = topic_by_subject.get(best_id)
        return _emit_end(
            RouterResult(
                subject=best_id,
                topic=topic,
                confidence=(
                    (CONFIDENCE_SUPPORTED if topic else CONFIDENCE_TOPIC)
                    if top >= 2.0
                    else (0.75 if topic else 0.6)
                ),
                status=STATUS_SUPPORTED,
            )
        )

    # ≥2 hits taxonomy → AMBIGUË (§14 : "réseaux" → informatiques/neuronaux)
    if len(unsupported_hits) >= 2:
        return _emit_end(
            RouterResult(
                subject=None,
                topic=None,
                confidence=0.5,
                status=STATUS_AMBIGUOUS,
                candidates=sorted(set(unsupported_hits)),
            )
        )

    # 1 hit taxonomy → unsupported (fallback tuteur général, pas de crash)
    if unsupported_hits:
        return _emit_end(
            RouterResult(
                subject=unsupported_hits[0],
                topic=None,
                confidence=CONFIDENCE_UNSUPPORTED,
                status=STATUS_UNSUPPORTED,
                candidates=sorted(set(unsupported_hits)),
            )
        )

    # 5) multi_domain : aucun alias, mais ≥2 domaines évoqués (§32 —
    #    identification seulement pour V4)
    domain_hits = set()
    for cfg in list_subjects():
        if _word_in(q_words, cfg.domain):
            domain_hits.add(cfg.domain)
    if len(domain_hits) >= 2:
        subs = [
            c.id
            for c in list_subjects()
            if c.domain in domain_hits
        ]
        return _emit_end(
            RouterResult(
                subject=None,
                topic=None,
                confidence=0.4,
                status=STATUS_MULTI_DOMAIN,
                subjects=sorted(subs),
            )
        )

    # 6) Rien identifié → unknown (tuteur général)
    return _emit_end(
        RouterResult(
            subject=None,
            topic=None,
            confidence=CONFIDENCE_LOW,
            status=STATUS_UNKNOWN,
        )
    )


def load_registry_ids() -> set[str]:
    """Ids du Subject Registry (helper — évite réimport circulaire)."""
    return {c.id for c in list_subjects()}
