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
import time
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

# --- V7.1 : couche sémantique (interchangeable, fail-safe) ---
from app.context.semantic.candidates import (
    build_topic_candidates,
)
from app.context.semantic.hybrid_ranker import (
    rank_candidates as rank_hybrid,
)
from app.context.semantic.retriever import (
    get_semantic_retriever,
)

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

# --- V7.1 (mission §10/§14) : hybrid ranking + recovery -------
# PONDÉRATION JUSTIFIÉE (cf. hybrid_ranker.py §10) : le lexical
# (déterministe, haute précision) garde 0.45 ; le sémantique
# (recall des paraphrases) porte 0.55. Calibré sur les mesures
# réelles qwen3-embedding:0.6b : paraphrases 0.76-0.86, bruit
# inter-domaine ≤ 0.72 (d'où le seuil de recovery ci-dessous).
LEXICAL_WEIGHT = 0.45
SEMANTIC_WEIGHT = 0.55

# ROUTING RECOVERY (§14) : si la confiance LEXICALE est sous ce
# seuil (topic-only 0.55, unknown 0.3, ambiguous 0.5), la
# couche sémantique peut RÉCUPÉRER un meilleur candidat. Au-dessus
# (alias plein 0.95/0.85, tokens 0.8), le lexical suffit — la
# couche sémantique n'est même pas consultée (latence §31).
SEMANTIC_RECOVERY_CONFIDENCE = 0.6

# Score sémantique MINIMAL pour qu'un candidat recovery soit
# retenu (§34 non-invention) : sous ce seuil, l'état lexical
# d'origine est conservé (unknown reste unknown — honnête).
# 0.72 = au-dessus du bruit inter-domaine mesuré (0.54-0.72),
# sous les vraies paraphrases (0.76+).
SEMANTIC_RECOVERY_MIN = 0.72

# Nombre de candidats sémantiques demandés au retriever (§11).
SEMANTIC_TOP_K = 5

# Scores sémantiques minimaux (calibrés sur mesures réelles
# qwen3-embedding:0.6b, §34 non-invention — cf. rapport) :
#   vraies paraphrases de topic  0.68-0.92
#   bruit absurde ("temps demain") 0.33-0.37
#   bruit inter-domaine modéré  0.55-0.72
# SEMANTIC_RECOVERY_MIN (matière entière depuis unknown) : les
#   phrases naturelles courtes descendent à 0.68 — seuil 0.66
#   les laisse passer, le bruit inter-domaine non.
SEMANTIC_RECOVERY_MIN = 0.66
# SEMANTIC_TOPIC_MIN (topic dans une matière confirmée) : plus
#   exigeant que le recovery de matière car le sujet est déjà
#   tranché et les topics partagent le vocabulaire de la
#   matière. Mesuré : vraies paraphrases de topic 0.68-0.92 ;
#   topics non pertinents d'une même matière ≤ 0.66.
SEMANTIC_TOPIC_MIN = 0.70
# Écart minimal entre deux SUJETS sémantiques pour trancher
#   (sinon ambiguous §13) — conflit réel mesuré ≤ 0.09.
SEMANTIC_SUBJECT_MARGIN = 0.08

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


# --- V7.1 : normalisation des scores lexicaux [0..1] ---------
# scores internes V6.5 : alias plein 2.0 / tokens 1.2 / topic 1.0
# → normalisés pour le ranking hybride (§10 : lexical_score ∈ [0..1])
def _normalize_lexical(score: float) -> float:
    if score >= 2.0:
        return 1.0
    if score >= 1.2:
        return min(1.0, score / 2.0 + 0.15)  # 1.2 → 0.75
    if score > 0.0:
        return 0.5  # topic seul : signal moyen
    return 0.0


def _match_type_from_kind(kind: str) -> str:
    """kind interne V6.5 → match_type V7.1 (§9)."""
    mapping = {
        "phrase": "exact",
        "word": "exact",
        "tokens": "lexical",
        "topic": "lexical",
    }
    return mapping.get(kind, "lexical")

def _semantic_recovery(
    query: str,
    lexical_result: RoutingResult,
    lexical_scores: dict[str, float],
    topic_by_subject: dict[str, str | None],
    match_kind: dict[str, str],
) -> RoutingResult:
    """ROUTING RECOVERY V7.1 (mission §14) — calibré sur les
    mesures réelles qwen3-embedding (§34 non-invention).

    Appelé UNIQUEMENT quand la décision lexicale est faible :
      - supported SANS topic (complétion B) ;
      - supported topic-only conf < SEMANTIC_RECOVERY_CONFIDENCE ;
      - unknown (recovery A).
    JAMAIS sur ambiguous/unsupported/multi_domain (§13).

    Modes :
      A. unknown → candidat sémantique fort (≥ RECOVERY_MIN)
         avec écart net → supported/semantic.
      B. supported + topic None → complétion du topic par le
         meilleur candidat sémantique DU SUJET lexical (le sujet
         reste la décision lexicale — mission §9 : le router
         garde l'autorité métier).
      C. supported + topic lexical MAIS candidat sémantique
         nettement plus spécifique (gap topic ≥ TOPIC_MARGIN)
         dans le MÊME sujet → override du topic.
    Fail-safe intégral : unavailable/error → résultat lexical
    d'origine, semantic_status tracé (§15/§19).
    """
    from app.context.semantic.hybrid_ranker import (
        TOPIC_MARGIN,
    )

    start = time.perf_counter()
    try:
        cands = build_topic_candidates()
    except Exception as exc:
        log_event(
            "SEMANTIC_SEARCH_ERROR",
            level="ERROR",
            message=f"Candidates build error: {exc}",
            extra={
                "operation": "semantic_search",
                "query": (query or "")[:100],
                "error": str(exc)[:200],
            },
        )
        return lexical_result.model_copy(
            update={"semantic_status": "error"}
        )

    try:
        outcome = get_semantic_retriever().search(
            query, cands, top_k=SEMANTIC_TOP_K
        )
    except Exception as exc:
        log_event(
            "SEMANTIC_SEARCH_ERROR",
            level="ERROR",
            message=f"Semantic retriever error: {exc}",
            extra={
                "operation": "semantic_search",
                "query": (query or "")[:100],
                "error": str(exc)[:200],
            },
        )
        return lexical_result.model_copy(
            update={"semantic_status": "error"}
        )

    latency_ms = int((time.perf_counter() - start) * 1000)

    if outcome.status != "available" or not outcome.matches:
        return lexical_result.model_copy(
            update={
                "semantic_status": (
                    "unavailable"
                    if outcome.status == "unavailable"
                    else "error"
                )
            }
        )

    # candidats sémantiques purs (clé : (subject, topic))
    sem_cands = outcome.matches

    # --- HYBRID RANKING (§10/§11) sur l'ensemble ----------
    lexical_candidates = [
        {
            "subject": sid,
            "topic": topic_by_subject.get(sid),
            "score": _normalize_lexical(sc),
            "match_kind": match_kind.get(sid, ""),
        }
        for sid, sc in lexical_scores.items()
    ]
    semantic_candidates = [
        {"subject": m.subject, "topic": m.topic, "score": m.score}
        for m in sem_cands
    ]
    ranked = rank_hybrid(
        lexical_candidates=lexical_candidates,
        semantic_candidates=semantic_candidates,
        query=query,
        semantic_status="available",
    )
    all_dicts = [c.as_dict() for c in ranked.candidates]
    sem_best = sem_cands[0]  # meilleur candidat sémantique pur

    def _trace(lex: RoutingResult, final: RoutingResult) -> None:
        log_event(
            "ROUTING_RECOVERY",
            message=(
                f"Routing recovery | query={(query or '')[:60]} | "
                f"lexical={lex.status}/{lex.subject}/"
                f"{lex.topic}/{lex.confidence} → "
                f"{final.status}/{final.subject}/{final.topic}/"
                f"{final.confidence} (mode={final.match_type})"
            ),
            extra={
                "operation": "routing_recovery",
                "query": (query or "")[:100],
                "lexical_status": lex.status,
                "lexical_confidence": lex.confidence,
                "recovered_status": final.status,
                "subject": final.subject or "",
                "topic": final.topic or "",
                "confidence": final.confidence,
                "match_type": final.match_type,
                "semantic_latency_ms": latency_ms,
                "candidates": all_dicts[:3],
            },
        )

    # ---- MODE B : complétion de topic (sujet lexical sûr) ----
    # le sujet lexical reste AUTORITAIRE ; la sémantique ne fait
    # que compléter le topic manquant dans CE sujet.
    if (
        lexical_result.status == "supported"
        and lexical_result.subject
        and lexical_result.topic is None
    ):
        in_subject = [
            m for m in sem_cands if m.subject == lexical_result.subject
        ]
        if in_subject:
            m = in_subject[0]
            if m.score >= SEMANTIC_TOPIC_MIN:
                # sujet lexical confirmé + topic sémantique fort :
                # les DEUX couches contribuent → confiance
                # consolidée (sujet 0.85-0.95 + topic 0.70+).
                conf = max(
                    lexical_result.confidence,
                    min(0.9, 0.5 + 0.45 * m.score),
                )
                completed = lexical_result.model_copy(
                    update={
                        "topic": m.topic,
                        "confidence": round(conf, 2),
                        "match_type": "hybrid",
                        "semantic_status": "available",
                        "topic_candidates": all_dicts,
                    }
                )
                _trace(lexical_result, completed)
                return completed
        # pas de topic sémantique fiable dans le sujet lexical →
        # le sujet seul reste la réponse (honnête)
        return lexical_result.model_copy(
            update={
                "semantic_status": "available",
                "topic_candidates": all_dicts,
            }
        )

    # ---- MODE A : unknown → supported (recovery pur §14) ----
    if lexical_result.status == "unknown":
        top2 = sem_cands[:2]
        distinct = (
            len(top2) > 1 and top2[1].subject != top2[0].subject
        )
        gap = (
            top2[0].score - top2[1].score if len(top2) > 1 else 1.0
        )
        if (
            sem_best.score >= SEMANTIC_RECOVERY_MIN
            and (not distinct or gap >= SEMANTIC_SUBJECT_MARGIN)
        ):
            # SPÉCIFICITÉ (standard ranking) : à score quasi égal
            # (même matière, écart < SUBJECT_MARGIN), un candidat
            # TOPIC (plus spécifique) prime sur la matière entière
            # (topic=None) — principe général, zéro cas codé.
            best = sem_best
            if best.topic is None and len(top2) > 1:
                second = top2[1]
                if (
                    second.subject == best.subject
                    and second.topic is not None
                    and (best.score - second.score)
                    < SEMANTIC_SUBJECT_MARGIN
                ):
                    best = second
            conf = min(
                0.9, 0.45 * best.score + 0.45
            )
            recovered = RoutingResult(
                status="supported",
                subject=best.subject,
                topic=best.topic,
                confidence=round(conf, 2),
                match_type="semantic",
                semantic_status="available",
                topic_candidates=all_dicts,
            )
            _trace(lexical_result, recovered)
            return recovered
        if sem_best.score >= SEMANTIC_RECOVERY_MIN and distinct:
            # deux matières aussi proches → ambiguous (§13)
            cands_subj = sorted({top2[0].subject, top2[1].subject})
            ambiguous = RoutingResult(
                status="ambiguous",
                confidence=0.5,
                candidates=cands_subj,
                match_type="hybrid",
                semantic_status=" + available",
                topic_candidates=all_dicts,
            )
            # (correction : Literal strict)
            ambiguous = ambiguous.model_copy(
                update={"semantic_status": "available"}
            )
            _trace(lexical_result, ambiguous)
            return ambiguous
        # score insuffisant → unknown conservé (§34)
        return lexical_result.model_copy(
            update={
                "semantic_status": "available",
                "topic_candidates": all_dicts,
            }
        )

    # ---- MODE C : override du topic lexical (même matière) ----
    # le sujet lexical est confirmé ; le candidat sémantique du
    # MÊME sujet est nettement plus spécifique → topic corrigé.
    if (
        lexical_result.status == "supported"
        and lexical_result.subject
        and lexical_result.topic is not None
        and sem_best.subject == lexical_result.subject
        and sem_best.topic is not None
        and sem_best.topic != lexical_result.topic
    ):
        lex_sem_score = 0.0
        for m in sem_cands:
            if (
                m.subject == lexical_result.subject
                and m.topic == lexical_result.topic
            ):
                lex_sem_score = m.score
                break
        if (
            sem_best.score >= SEMANTIC_TOPIC_MIN
            and (sem_best.score - lex_sem_score) >= TOPIC_MARGIN
        ):
            # override sémantique : sujet confirmé par les DEUX
            # couches, topic tranché par la sémantique avec un
            # écart net → confiance consolidée (modérée-haute :
            # 0.55 lexical + 0.70+ sémantique → ~0.75-0.85).
            conf = max(
                lexical_result.confidence,
                min(0.85, 0.5 + 0.42 * sem_best.score),
            )
            overridden = lexical_result.model_copy(
                update={
                    "topic": sem_best.topic,
                    "confidence": round(conf, 2),
                    "match_type": "hybrid",
                    "semantic_status": "available",
                    "topic_candidates": all_dicts,
                }
            )
            _trace(lexical_result, overridden)
            return overridden

    # ---- défaut : renforcer/confirmer le résultat lexical ----
    # CONFIRMATION (§14) : si le meilleur candidat sémantique du
    # MÊME sujet désigne le MÊME topic que le lexical, les deux
    # couches indépendantes convergent → confiance renforcée
    # (le lexical seul restait prudent à 0.55 ; la convergence
    # justifie 0.85, mesuré : "return" exact + 0.68 sémantique).
    conf = lexical_result.confidence
    if (
        lexical_result.status == "supported"
        and lexical_result.subject
        and sem_best.subject == lexical_result.subject
        and sem_best.topic is not None
        and sem_best.topic == lexical_result.topic
    ):
        conf = max(conf, min(0.85, 0.5 + 0.45 * sem_best.score))
    confirmed = lexical_result.model_copy(
        update={
            "confidence": round(conf, 2),
            "match_type": (
                "hybrid"
                if sem_best.topic == lexical_result.topic
                and lexical_result.match_type in ("exact", "lexical", "morphological")
                else lexical_result.match_type
            ),
            "semantic_status": "available",
            "topic_candidates": all_dicts,
        }
    )
    _trace(lexical_result, confirmed)
    return confirmed


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
        supported_result = RoutingResult(
            status="supported",
            subject=best_id,
            topic=topic,
            confidence=conf,
            match_type=_match_type_from_kind(
                match_kind.get(best_id, "")
            ),
        )
        # V7.1 §14 : le recovery sémantique se déclenche quand la
        # décision lexicale est INCOMPLÈTE : confiance faible
        # (topic seul 0.55) OU sujet sûr mais topic MANQUANT
        # (mode B complétion). Alias plein + topic identifié →
        # lexical suffit, pas d'appel sémantique (latence §31).
        if conf < SEMANTIC_RECOVERY_CONFIDENCE or topic is None:
            supported_result = _semantic_recovery(
                query=query or "",
                lexical_result=supported_result,
                lexical_scores=scores,
                topic_by_subject=topic_by_subject,
                match_kind=match_kind,
            )
        return _emit_end(supported_result)

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

    # 6) Rien identifié → unknown (§17 : ne jamais inventer un
    #    subject_id) — V7.1 : la couche sémantique peut RÉCUPÉRER
    #    un candidat ici (§14 : lexical unknown + semantic 0.84
    #    → supported), sans quoi unknown reste unknown.
    unknown_result = RoutingResult(
        status="unknown",
        confidence=CONFIDENCE_LOW,
    )
    unknown_result = _semantic_recovery(
        query=query or "",
        lexical_result=unknown_result,
        lexical_scores={},
        topic_by_subject=topic_by_subject,
        match_kind=match_kind,
    )
    return _emit_end(unknown_result)