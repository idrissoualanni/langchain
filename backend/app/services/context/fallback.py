from app.schemas.context import FallbackDecision
from app.logging.events import log_event

__all__ = [
    "decide_fallback",
    "fallback_note_for_prompt",
    "is_vague_query",
]

# Seuil heuristique §9 : une requête « très courte/vague » a peu
# de tokens significatifs (< 3) → clarification ; une question
# compréhensible mais non routée → general tutor.
_VAGUE_MIN_TOKENS = 3


def is_vague_query(query: str) -> bool:
    """§9 : requête très courte/vague ?

    « Aide-moi » → vague (1 token) → clarification.
    « Pourquoi le ciel est bleu ? » → 5 tokens → general tutor.
    Heuristique documentée : compte les tokens alphabétiques.
    """
    import re

    toks = re.findall(r"[a-zà-ÿ0-9]{2,}", (query or "").lower())
    return len(toks) < _VAGUE_MIN_TOKENS


def decide_fallback(
    routing_status: str,
    subject: str | None = None,
    topic: str | None = None,
    knowledge_status: str = "unavailable",
    web_status: str = "unavailable",
    has_web_results: bool = False,
    query: str = "",
    user_id: str = "",
    thread_id: str = "",
) -> FallbackDecision:
    """MATRICE DE DÉCISION §6 — fonction PURE (aucun LLM, aucun
    appel externe, aucun effet de bord hors logging).

    | Routing      | Knowledge    | Web         | Action                     |
    |-------------|--------------|-------------|----------------------------|
    | supported   | found        | non requis  | use_local_knowledge        |
    | supported   | insufficient | found       | use_web_search             |
    | supported   | insufficient | other       | use_general_tutor          |
    | supported   | error*       | found       | use_web_search             |
    | ambiguous   | n/a          | n/a         | ask_clarification          |
    | unknown     | n/a          | n/a         | ask_clarification **       |
    | unsupported | n/a          | n/a         | use_general_tutor          |
    | multi_domain| n/a          | n/a         | ask_clarification          |

    * knowledge "error" est replié en "insufficient" par la
      recherche locale V6.5 (l'erreur est loggée) — le paramètre
      reste accepté pour la complétude du contrat.
    ** unknown : vague → clarification ; compréhensible →
      use_general_tutor (§9, is_vague_query).

    knowledge_status="unavailable" sur matière supportée (aucune
    source déclarée) ≈ insufficient : le web peut être tenté —
    mais SANS résultat web c'est General Tutor (§12 : supported
    + knowledge insuffisant ≠ unsupported).
    """
    log_event(
        "FALLBACK_START",
        message=(
            f"Fallback eval | routing={routing_status} | "
            f"knowledge={knowledge_status} | web={web_status}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        extra={
            "operation": "fallback",
            "routing_status": routing_status,
            "knowledge_status": knowledge_status,
            "web_status": web_status,
            "subject": subject or "",
            "topic": topic or "",
        },
    )

    decision = _decide(
        routing_status=routing_status,
        knowledge_status=knowledge_status,
        web_status=web_status,
        has_web_results=has_web_results,
        query=query,
        subject=subject,
        topic=topic,
    )

    log_event(
        "FALLBACK_DECISION",
        message=(
            f"Fallback decision | action={decision.action} | "
            f"reason={decision.reason[:80]}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        extra={
            "operation": "fallback",
            "action": decision.action,
            "reason": decision.reason,
            "subject": subject or "",
            "topic": topic or "",
            "routing_status": routing_status,
            "knowledge_status": knowledge_status,
            "web_status": web_status,
        },
    )
    return decision


def _decide(
    routing_status: str,
    knowledge_status: str,
    web_status: str,
    has_web_results: bool,
    query: str,
    subject: str | None,
    topic: str | None,
) -> FallbackDecision:
    """Cœur pur de la matrice — séparé pour la testabilité."""

    # --- Routing non-supported : le knowledge/web ne comptent pas
    if routing_status == "ambiguous":
        return FallbackDecision(
            action="ask_clarification",
            reason=(
                "La question est ambiguë entre plusieurs "
                "matières — demander une clarification à "
                "l'étudiant plutôt que de choisir arbitrairement."
            ),
            source_status=routing_status,
            confidence=0.5,
        )

    if routing_status == "multi_domain":
        return FallbackDecision(
            action="ask_clarification",
            reason=(
                "Plusieurs domaines sont évoqués — demander le "
                "domaine principal visé avant de construire le "
                "contexte."
            ),
            source_status=routing_status,
            confidence=0.4,
        )

    if routing_status == "unsupported":
        return FallbackDecision(
            action="use_general_tutor",
            reason=(
                "Matière détectée mais non configurée (aucun "
                "SubjectConfig) — tuteur général, sans config "
                "ni knowledge ni tool fabriqués."
            ),
            source_status=routing_status,
            confidence=0.9,
        )

    if routing_status == "unknown":
        # §9 : vague → clarification ; compréhensible → tutor
        if is_vague_query(query):
            return FallbackDecision(
                action="ask_clarification",
                reason=(
                    "Requête trop courte ou vague, aucun sujet "
                    "identifiable — demander une précision."
                ),
                source_status=routing_status,
                confidence=0.3,
            )
        return FallbackDecision(
            action="use_general_tutor",
            reason=(
                "Aucune matière identifiée mais la question est "
                "compréhensible — tuteur général."
            ),
            source_status=routing_status,
            confidence=0.4,
        )

    # --- Routing supported : la cascade knowledge → web (§12/§13)
    if routing_status == "supported":
        if knowledge_status == "found":
            return FallbackDecision(
                action="use_local_knowledge",
                reason=(
                    "Knowledge local pertinent trouvé — contexte "
                    "de cours utilisé directement."
                ),
                source_status="supported/found",
                confidence=0.95,
            )
        # insufficient / unavailable / error → web ?
        web_ok = web_status == "found" and has_web_results
        if web_ok:
            return FallbackDecision(
                action="use_web_search",
                reason=(
                    "Knowledge local insuffisant pour une matière "
                    "supportée — recherche web pertinente "
                    "disponible."
                ),
                source_status=(
                    f"supported/{knowledge_status}/web_found"
                ),
                confidence=0.7,
            )
        reason_map = {
            "unavailable": (
                "web search indisponible (service ou clé absent)"
            ),
            "error": "recherche web en échec technique",
            "insufficient": (
                "recherche web sans résultat pertinent"
            ),
        }
        return FallbackDecision(
            action="use_general_tutor",
            reason=(
                f"Knowledge local insuffisant et "
                f"{reason_map.get(web_status, 'web inutilisable')} "
                "— tuteur général transparent."
            ),
            source_status=(
                f"supported/{knowledge_status}/web_{web_status}"
            ),
            confidence=0.5,
        )

    # Statut inattendu (défense en profondeur — jamais de crash)
    return FallbackDecision(
        action="continue_without_external_search",
        reason=(
            f"Statut de routing inattendu « {routing_status} » — "
            "continuer sans recherche externe."
        ),
        source_status=routing_status or "empty",
        confidence=0.1,
    )


def fallback_note_for_prompt(decision: FallbackDecision) -> str:
    """§8 : note de fallback TRANSPARENTE pour le prompt LLM.

    Explique la RAISON du fallback au modèle (il peut la
    reformuler naturellement). Le frontend étudiant n'affiche
    PAS ces détails techniques par défaut (§32) — seule
    l'interface développeur/inspector les montre.
    """
    notes = {
        "use_local_knowledge": "",  # pas un fallback — rien à dire
        "use_web_search": (
            "NOTE DU SYSTÈME — la base de cours locale n'avait "
            "rien de pertinent pour cette question ; une "
            "recherche web a été tentée et a fourni des sources. "
            "Appuie-toi sur la section RECHERCHE WEB et cite "
            "naturellement ces sources."
        ),
        "use_general_tutor": (
            "NOTE DU SYSTÈME — " + decision.reason + " Réponds "
            "avec tes connaissances générales, signale "
            "honnêtement que ce contenu ne provient pas d'une "
            "base de cours vérifiée."
        ),
        "ask_clarification": (
            "NOTE DU SYSTÈME — " + decision.reason
        ),
        "continue_without_external_search": (
            "NOTE DU SYSTÈME — " + decision.reason
        ),
    }
    return notes.get(decision.action, "")
