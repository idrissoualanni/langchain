# Subject Router V5 — classification « de quoi parle la demande ? » (§15)
#
# Sortie : RoutingResult (pydantic VALIDÉ, §14) — plus de dataclass
# custom. Le router ne décide JAMAIS de la réponse, ne construit
# JAMAIS le contexte : il classifie uniquement.
#
# Statuts (§13-§19) :
#   supported   → matière configurée identifiée
#   ambiguous   → plusieurs interprétations (candidates) → clarification
#   unsupported → matière détectée mais non configurée → General Tutor
#   unknown     → rien d'identifié → General Tutor
#   multi_domain→ plusieurs domaines évoqués (identification)
#
# Sources de vérité (§13) :
#   - Subject Registry (aliases/topics des SubjectConfig YAML)
#   - Taxonomy (matières détectables non configurées)
#   AUCUNE liste de keywords codée en dur dans CE module.
#
# V6.5 (§8/§9/§10) : le matching des aliases/topics utilise la
# normalisation contrôlée (query_norm) — variante morphologique
# singulier/pluriel (fonction ≈ fonctions) et aliases multi-mots
# par COUVERTURE DE TOKENS (ordre libre) en plus de la phrase
# exacte. La confiance est graduée : alias plein (phrase) > alias
# par tokens > topic seul > domaine. Toujours déterministe.
import re
import unicodedata

from app.context.query_norm import (
    normalize_query,
    normalize_tokens,
    variant_forms,
)
from app.context.schemas import RoutingResult
from app.logging.events import log_event
from app.subjects.registry import get_subject, list_subjects
from app.subjects.taxonomy import active_taxonomy

# Confidences par situation (documentation du comportement)
CONFIDENCE_SUPPORTED = 0.95   # alias plein + topic identifié
CONFIDENCE_TOPIC = 0.85       # alias plein sans topic
CONFIDENCE_UNSUPPORTED = 0.9  # matière taxonomy détectée non configurée
CONFIDENCE_LOW = 0.3          # rien d'identifié
# V6.5 : alias matché par couverture de tokens (paraphrase,
# ordre différent) — légèrement sous la phrase exacte.
CONFIDENCE_TOKENS = 0.8
# V6.5 : topic identifié sans alias matière — le topic est fort
# (les topics sont spécifiques), mais sans confirmation du
# contexte matière la confiance est modérée.
CONFIDENCE_TOPIC_ONLY = 0.55

_WORD_RE = re.compile(r"[a-z0-9]+")


def _strip_accents(text: str) -> str:
    """Normalise accents (NFD fold) — matching FR indépendant des accents."""
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
    return _norm(phrase) in text_norm


def _word_in(q_words: set[str], word: str) -> bool:
    """Mot simple : frontière de mots (py ≠ manipulation) — V6.5 :
    variantes morphologiques testées (fonction ≈ fonctions)."""
    w = _norm(word)
    if not w:
        return False
    if w in q_words:
        return True
    return any(v in q_words for v in variant_forms(w))


def _alias_tokens_covered(
    q_words: set[str], alias: str
) -> bool:
    """V6.5 §8 : alias multi-mots reconnu par COUVERTURE de
    tokens (ordre libre) — « communication entre ordinateurs »
    couvre « communiquent ... ordinateurs » après normalisation
    morphologique (communiquent/communication partagent le
    stem « communiqu » ? NON — la couverture teste les tokens
    ET leurs variantes ; ici c'est l'ALIAS qui varie). Seuls les
    tokens signifiants de l'alias comptent (stop-words exclus).
    """
    toks = normalize_tokens(alias)
    sig = [t for t in toks if len(t) >= 3 and t not in _ALIAS_STOP]
    if not sig:
        return False
    covered = all(
        _word_in(q_words, t) for t in sig
    )
    return covered


# Stop-words pour la couverture d'alias (petits mots outils)
_ALIAS_STOP = {
    "les", "des", "une", "entre", "avec", "dans", "pour", "par",
    "sur", "est", "sont", "que", "qui", "quoi", "comment", "quoi",
    "the", "and", "for", "with", "les", "lui", "leur", "tout",
}


def _match_topic(cfg, q_words: set[str], text_norm: str) -> str | None:
    """Topic du SubjectConfig présent dans la question — V6.5 :
    phrase exacte OU variante morphologique de token."""
    for topic in cfg.topics:
        t = _norm(topic)
        if " " in t or "/" in t:
            if t in text_norm:
                return topic
        elif t and _word_in(q_words, topic):
            return topic
    return None


def _emit_end(result: RoutingResult) -> RoutingResult:
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
) -> RoutingResult:
    """Classe une question → RoutingResult validé (sans LLM).

    hint_subject : matière transmise explicitement (API preview,
    futur HITL) — l'emporte si configurée.
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
                RoutingResult(
                    status="supported",
                    subject=cfg.id,
                    topic=topic,
                    confidence=(
                        CONFIDENCE_SUPPORTED
                        if topic
                        else CONFIDENCE_TOPIC
                    ),
                )
            )

    # 2) Scoring des matières CONFIGURÉES (aliases + topics du Registry)
    #    V6.5 : alias plein (phrase exacte) = 2.0 ; alias par
    #    couverture de tokens (paraphrase, ordre libre) = 1.2 ;
    #    topic identifié = 1.0.
    scores: dict[str, float] = {}
    topic_by_subject: dict[str, str | None] = {}
    match_kind: dict[str, str] = {}
    for cfg in list_subjects():
        score = 0.0
        kind = ""
        for alias in sorted(cfg.aliases, key=len, reverse=True):
            a = _norm(alias)
            if " " in a or "/" in a:
                if _phrase_in(text_norm, alias):
                    score = max(score, 2.0)
                    kind = "phrase"
                    break
                if _alias_tokens_covered(q_words, alias):
                    score = max(score, 1.2)
                    kind = kind or "tokens"
            else:
                if _word_in(q_words, alias):
                    score = max(score, 2.0)
                    kind = "word"
                    break
        topic = _match_topic(cfg, q_words, text_norm)
        topic_by_subject[cfg.id] = topic
        if topic:
            score = max(score, 1.0)
            kind = kind or "topic"
        if score > 0:
            scores[cfg.id] = score
            match_kind[cfg.id] = kind

    # 3) Détection taxonomy (matières non-configurées).
    #    Anti-collision sur les HITS : une entrée taxonomy dont l'id
    #    est configuré ne compte que si le YAML n'a pas matché.
    registry_ids = {c.id for c in list_subjects()}
    configured_hit_ids = set(scores.keys())
    unsupported_hits: list[str] = []
    for taxo in active_taxonomy(set()):
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
        kind = match_kind.get(best_id, "")

        # Égalité parfaite entre matières configurées → ambiguous
        if len(scores) >= 2 and top == second:
            return _emit_end(
                RoutingResult(
                    status="ambiguous",
                    confidence=0.5,
                    candidates=sorted(scores.keys()),
                )
            )

        topic = topic_by_subject.get(best_id)
        # Confiance graduée V6.5 (§10) :
        #   phrase/mot exact (2.0) → 0.95/0.85
        #   couverture tokens (1.2, paraphrase) → 0.8
        #   topic seul (1.0) → 0.55
        if top >= 2.0:
            conf = (
                CONFIDENCE_SUPPORTED
                if topic
                else CONFIDENCE_TOPIC
            )
        elif top >= 1.2:
            conf = CONFIDENCE_TOKENS
        else:
            conf = CONFIDENCE_TOPIC_ONLY
        return _emit_end(
            RoutingResult(
                status="supported",
                subject=best_id,
                topic=topic,
                confidence=conf,
            )
        )

    # ≥2 hits taxonomy → AMBIGUË (§18 : « les réseaux »)
    if len(unsupported_hits) >= 2:
        return _emit_end(
            RoutingResult(
                status="ambiguous",
                confidence=0.5,
                candidates=sorted(set(unsupported_hits)),
            )
        )

    # 1 hit taxonomy → unsupported (§19 : General Tutor)
    if unsupported_hits:
        return _emit_end(
            RoutingResult(
                status="unsupported",
                subject=unsupported_hits[0],
                confidence=CONFIDENCE_UNSUPPORTED,
                candidates=sorted(set(unsupported_hits)),
            )
        )

    # 5) multi_domain : ≥2 domaines évoqués (§32)
    domain_hits = set()
    for cfg in list_subjects():
        if _word_in(q_words, cfg.domain):
            domain_hits.add(cfg.domain)
    if len(domain_hits) >= 2:
        subs = [
            c.id for c in list_subjects() if c.domain in domain_hits
        ]
        return _emit_end(
            RoutingResult(
                status="multi_domain",
                confidence=0.4,
                subjects=sorted(subs),
            )
        )

    # 6) Rien identifié → unknown (§17 : ne jamais inventer un subject_id)
    return _emit_end(
        RoutingResult(
            status="unknown",
            confidence=CONFIDENCE_LOW,
        )
    )
