# Tools pédagogiques communs — V4.1 réels + V5.2 INTERACTIFS.
#
# VRAIES implémentations branchées sur la base knowledge réelle
# (app/knowledge/) : chaque exercice/évaluation/indice est généré
# depuis le CONTENU du cours, jamais inventé.
#
# V5.2 — WORKFLOW INTERACTIF (brief V5.2 §4-§13) :
#   create_exercise → passe le thread en ACTIVITÉ EN COURS
#     (status=waiting_for_answer). Le LLM doit poser la question et
#     S'ARRÊTER. L'exercice n'est PAS terminé à la génération.
#   evaluate_answer → évalue, met à jour l'activité (attempts, score)
#     et guide : feedback → question de compréhension, ou hint → retry.
#   give_hint       → indices PROGRESSIFS 0→1→2 trackés dans l'état
#     d'activité (hint_level) : jamais la solution complète d'emblée.
#   create_quiz     → quiz CONVERSATIONNEL : une question à la fois,
#     la suivante n'est livrée qu'après réponse évaluée (§17-§20).
#   assess_understanding → distingue réponse correcte de compréhension
#     réelle ; retour structuré understood/partial/unclear (§12). Ce
#     n'est PAS un mastery — rien n'écrit dans le Learning Profile.
#   propose_review  → propose une révision ciblée depuis les topics
#     réellement disponibles (jamais inventés).
#
# MÉCANISME : chaque tool retourne Command(update={...}) — mécanisme
# NATIF LangGraph. L'état d'activité vit dans CustomAgentState
# (thread-local, persisté par le checkpointer §16). Aucun stockage
# manuel parallèle, aucune modification de graph.py/runner.py.
from __future__ import annotations

import re
import time
import unicodedata
from typing import Annotated

from langchain.tools import InjectedState, InjectedToolCallId
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.config import RunnableConfig
from langgraph.types import Command

from app.agent.activity_state import (
    ACTIVITY_CHECKING_UNDERSTANDING,
    ACTIVITY_COMPLETED,
    ACTIVITY_TYPE_EXERCISE,
    ACTIVITY_TYPE_QUIZ,
    ACTIVITY_WAITING_ANSWER,
    ACTIVITY_WAITING_RETRY,
    RESPONSE_TYPE_CODE,
    RESPONSE_TYPE_SHORT_ANSWER,
    new_activity_id,
)
from app.context.knowledge_retriever import (
    KNOWLEDGE_DIR,
    _split_sections,
)
from app.logging.events import log_event

# Mots trop courants retirés du scoring d'évaluation
_EVAL_STOP_WORDS = {
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "ou",
    "en", "dans", "pour", "par", "sur", "est", "sont", "avec", "que",
    "qui", "quoi", "ce", "cet", "cette", "ces", "aux", "au", "a",
    "plus", "moins", "très", "tres", "peut", "être", "etre", "comme",
    "the", "is", "are", "of", "and", "or", "to", "in", "it",
}


# ------------------------------------------------------------------
# Helpers knowledge (réels, inchangés dans leur logique)
# ------------------------------------------------------------------


def _find_section(subject: str, topic: str) -> dict | None:
    """Cherche la section knowledge (source + topic + content) d'un
    topic donné d'une matière. Retour None si introuvable.

    Pont Registry ↔ knowledge (mission intégration) : le router V4
    route des topics REGISTRY (« fonctions ») alors que les
    fichiers knowledge sont découpés en SECTIONS (« definition »).
    Résolution en 2 étapes, sans hardcoding :
      1. le topic EST une section (comportement V4.1 inchangé) ;
      2. sinon, s'il est un topic Registry, on résout son fichier
         knowledge (stem ou titre H1 — cf. resolve_topic_source)
         et on prend sa PREMIÈRE section réelle (pas « _intro »,
         qui est ambigu : chaque fichier en a un).
    """
    from app.subjects.registry import get_subject

    cfg = get_subject(subject)
    if cfg is None:
        return None

    topic_norm = _strip_accents((topic or "").lower())

    # « _intro » est ambigu (présent dans chaque fichier) :
    # on ne le résout JAMAIS en section d'exercice — le LLM est
    # guidé vers les topics réels (§38 : pas d'invention).
    from app.context.knowledge_retriever import resolve_topic_source

    resolved = resolve_topic_source(subject, topic)
    src_yaml_resolved = resolved[0] if resolved else None
    for src in cfg.knowledge.get("sources", []):
        path = KNOWLEDGE_DIR / f"{src}.md"
        if not path.exists():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue
        sections = _split_sections(content)
        for sec_topic, sec_content in sections:
            if (
                sec_topic != "_intro"
                and _strip_accents(sec_topic.lower()) == topic_norm
            ):
                return {
                    "source": f"{path.parent.name}/{path.stem}",
                    "topic": sec_topic,
                    "content": sec_content,
                }

        # Pont Registry : topic Registry (ex: fonctions, boucles)
        # → fichier knowledge correspondant → première section
        # réelle (definition / for / classes...).
        if src_yaml_resolved and src == src_yaml_resolved:
            real_sections = [
                (t, c)
                for t, c in sections
                if t != "_intro" and c.strip()
            ]
            if real_sections:
                sec_topic, sec_content = real_sections[0]
                return {
                    "source": f"{path.parent.name}/{path.stem}",
                    "topic": sec_topic,
                    "content": sec_content,
                }
    return None


def _available_topics(subject: str) -> list[str]:
    """Topics réellement disponibles (sections knowledge présentes)."""
    from app.subjects.registry import get_subject

    cfg = get_subject(subject)
    if cfg is None:
        return []
    topics: list[str] = []
    for src in cfg.knowledge.get("sources", []):
        path = KNOWLEDGE_DIR / f"{src}.md"
        if not path.exists():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for sec_topic, _ in _split_sections(content):
            if sec_topic and sec_topic != "_intro":
                topics.append(sec_topic)
    return topics


def _strip_accents(text: str) -> str:
    return "".join(
        ch
        for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )


def _key_terms(content: str, max_terms: int = 6) -> list[str]:
    """Termes-clés d'une section knowledge : mots signifiants les plus
    longs (heuristique: les termes techniques sont les plus longs)."""
    raw = re.findall(r"[a-z0-9]{4,}", _strip_accents(content.lower()))
    counts: dict[str, int] = {}
    for w in raw:
        if w in _EVAL_STOP_WORDS:
            continue
        counts[w] = counts.get(w, 0) + 1
    # Score = longueur * fréquence ; le tri capture le vocabulaire technique
    ranked = sorted(
        counts, key=lambda w: len(w) * (1 + counts[w]), reverse=True
    )
    return ranked[:max_terms]


def _content_tokens(content: str) -> set[str]:
    return {
        w
        for w in re.findall(
            r"[a-z0-9]{3,}", _strip_accents(content.lower())
        )
        if w not in _EVAL_STOP_WORDS
    }


# ------------------------------------------------------------------
# Helpers state d'activité
# ------------------------------------------------------------------


def _thread_ids(config: RunnableConfig | None) -> tuple[str, str]:
    """(user_id, thread_id) pour les logs — depuis la config du run."""
    conf = (config or {}).get("configurable", {}) or {}
    return (
        conf.get("user_id", "") or "",
        conf.get("thread_id", "") or "",
    )


def _activity_log_entry(
    event: str,
    status: str,
    detail: str = "",
    hint_level: int = 0,
    activity_type: str = "",
) -> dict:
    """Entrée de journal d'activité (consommée par le frontend §42)."""
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "event": event,
        "status": status,
        "detail": detail[:300],
        "hint_level": hint_level,
        "activity_type": activity_type,
    }


def _is_code_subject(subject: str) -> bool:
    """Le subject autorise-t-il les exercices de code ? Générique :
    se base sur les tools déclarés par la SubjectConfig — jamais un
    if subject == 'python' (§38 indépendance matières)."""
    from app.subjects.registry import get_subject

    cfg = get_subject(subject)
    if cfg is None:
        return False
    specialized = cfg.tools.get("specialized", [])
    return any(
        tool in specialized
        for tool in ("execute_code", "execute_python")
    )


def _expected_response_type(subject: str, topic: str) -> str:
    """Type de réponse attendu (§23) : code si la matière expose
    execute_code, sinon réponse courte/texte — générique."""
    if _is_code_subject(subject):
        return RESPONSE_TYPE_CODE
    return RESPONSE_TYPE_SHORT_ANSWER


def _help_with(
    tool_name: str, subject: str, topic: str, level: int = 0
) -> str:
    """Rappel d'usage standard d'un tool pédagogique dans une réponse."""
    return (
        f"[tool {tool_name}] Pour aller plus loin : "
        f"{tool_name}(subject='{subject}', topic='{topic}'"
        + (f", level={level})" if level is not None else ")")
    )


# ------------------------------------------------------------------
# EXERCICE INTERACTIF (§4-§6, §22-§23)
# ------------------------------------------------------------------


@tool
def create_exercise(
    subject: str,
    topic: str,
    state: Annotated[dict | None, InjectedState] = None,
    tool_call_id: Annotated[str | None, InjectedToolCallId] = None,
    config: RunnableConfig = None,
) -> Command:
    """Crée un exercice INTERACTIF sur un topic d'une matière et ouvre
    une activité pédagogique en cours dans CE thread.

    Après ce tool : le thread passe en « waiting_for_answer ». Pose la
    question à l'étudiant dans TA réponse finale, puis ATTENDS sa
    réponse. NE DONNE NI la solution, NI la correction, NI la question
    suivante dans le même tour.

    L'exercice est construit depuis la base knowledge réelle (source,
    topic, contenu du cours) — jamais inventé. Si le topic est
    introuvable, le retour liste les topics disponibles.

    Args:
        subject: id de la matière (ex: "python", "biology",
            "mathematics", "computer_networks").
        topic: le sujet demandé par l'étudiant, tel quel (ex:
            "fonctions", "return", "boucles", "membrane"). Le
            tool résout AUTOMATiquement un sujet large vers la
            section knowledge correspondante (« fonctions » →
            definition) — appelle-le IMMÉDIATEMENT avec le sujet
            demandé, sans demander à l'étudiant de choisir un
            sous-aspect. Les topics section précis (ex: "return",
            "while") fonctionnent aussi.
    """
    user_id, thread_id = _thread_ids(config)
    log_event(
        "TOOL_CALL",
        message=f"create_exercise subject={subject} topic={topic}",
        tool_name="create_exercise",
        user_id=user_id,
        thread_id=thread_id,
    )

    section = _find_section(subject, topic)
    if section is None:
        from app.subjects.registry import get_subject

        cfg = get_subject(subject)
        available = ", ".join(_available_topics(subject)) or (
            ", ".join(cfg.topics) if cfg else "matière inconnue"
        )
        log_event(
            "TOOL_ERROR",
            level="WARNING",
            message=(
                f"create_exercise: topic '{topic}' introuvable "
                f"pour '{subject}'"
            ),
            tool_name="create_exercise",
            user_id=user_id,
            thread_id=thread_id,
        )
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            f"Aucune section knowledge pour le topic "
                            f"'{topic}' de '{subject}'. Topics "
                            f"disponibles : {available}. Propose un "
                            "choix à l'étudiant — n'invente pas "
                            "d'exercice."
                        ),
                        tool_call_id=tool_call_id or "",
                    )
                ]
            }
        )

    terms = _key_terms(section["content"], max_terms=4)
    src = section["source"]
    resp_type = _expected_response_type(subject, topic)
    activity_id = new_activity_id(subject, topic)
    question = (
        f"Explique avec tes mots ce qu'est « {section['topic']} » "
        f"dans le contexte de {subject}, en mentionnant : "
        f"{', '.join(terms[:3])}."
    )

    # ---- Activity State : l'activité est EN COURS (§4) ----
    activity = {
        "activity_id": activity_id,
        "activity_type": ACTIVITY_TYPE_EXERCISE,
        "subject": subject,
        "topic": section["topic"],
        "status": ACTIVITY_WAITING_ANSWER,
        "question": question,
        "expected_response_type": resp_type,
        "source": src,
        "hint_level": 0,
        "attempts": 0,
        "awaiting_answer": True,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    exercise = (
        f"ACTIVITÉ OUVERTE — exercice {subject}/{section['topic']} "
        f"(source : {src}, id : {activity_id}).\n\n"
        f"Question : {question}\n\n"
        f"Pour bien répondre :\n"
        f"- définis {section['topic']} précisément ;\n"
        f"- utilise les termes : {', '.join(terms)} ;\n"
        f"- donne un exemple concret.\n\n"
        f"Type de réponse attendu : {resp_type}.\n\n"
        f"COMPORTEMENT : le thread est maintenant en "
        f"waiting_for_answer. Pose CETTE question à l'étudiant, "
        f"accompagne-la d'un exemple d'attente (ex : « À toi. ») et "
        f"TERMINE ton tour. Ne donne ni solution ni correction ni "
        f"question suivante. Quand l'étudiant répond, utilise "
        f"evaluate_answer (subject='{subject}', "
        f"topic='{section['topic']}', answer=<réponse mot pour mot>)."
    )

    log_event(
        "ACTIVITY_STARTED",
        message=(
            f"Exercise started | {subject}/{section['topic']} | "
            f"status={ACTIVITY_WAITING_ANSWER} | source={src}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        tool_name="create_exercise",
        extra={
            "activity_id": activity_id,
            "subject": subject,
            "topic": section["topic"],
            "status": ACTIVITY_WAITING_ANSWER,
            "source": src,
        },
    )
    log_event(
        "ACTIVITY_WAITING",
        message="Exercise waiting for student answer",
        user_id=user_id,
        thread_id=thread_id,
        tool_name="create_exercise",
        extra={"activity_id": activity_id, "status": ACTIVITY_WAITING_ANSWER},
    )

    return Command(
        update={
            "learning_activity": activity,
            "activity_log": [
                _activity_log_entry(
                    "ACTIVITY_STARTED",
                    ACTIVITY_WAITING_ANSWER,
                    f"exercise {subject}/{section['topic']}",
                    0,
                    ACTIVITY_TYPE_EXERCISE,
                ),
                _activity_log_entry(
                    "ACTIVITY_WAITING",
                    ACTIVITY_WAITING_ANSWER,
                    "waiting for student answer",
                    0,
                    ACTIVITY_TYPE_EXERCISE,
                ),
            ],
            "messages": [
                ToolMessage(
                    content=exercise,
                    tool_call_id=tool_call_id or "",
                )
            ],
        }
    )


# ------------------------------------------------------------------
# ÉVALUATION + VÉRIFICATION DE COMPRÉHENSION (§10-§13)
# ------------------------------------------------------------------


@tool
def evaluate_answer(
    subject: str,
    topic: str,
    answer: str,
    state: Annotated[dict | None, InjectedState] = None,
    tool_call_id: Annotated[str | None, InjectedToolCallId] = None,
    config: RunnableConfig = None,
) -> Command:
    """Évalue la réponse d'un étudiant sur un topic, par couverture du
    contenu réel du cours, et met à jour l'activité en cours du thread.

    Scoring déterministe : proportion des termes-clés de la section
    knowledge couverts par la réponse + retour formatif (termes
    manquants, prochaine étape). PAS une simulation : le score vient
    de la comparaison réponse ↔ base de cours.

    Après évaluation, le retour t'indique la réaction pédagogique à
    choisir :
      - score élevé   → félicite PUIS vérifie la compréhension réelle
        avec assess_understanding (§11) avant d'enchaîner ;
      - score moyen   → reconnais ce qui est juste, demande de
        développer les points manquants (ou give_hint level 0) ;
      - score faible  → oriente avec give_hint level=0, laisse
        réessayer.

    Args:
        subject: id de la matière (ex: "python").
        topic: le topic évalué (ex: "return").
        answer: la réponse de l'étudiant, mot pour mot.
    """
    user_id, thread_id = _thread_ids(config)
    log_event(
        "TOOL_CALL",
        message=(
            f"evaluate_answer subject={subject} topic={topic} "
            f"answer={len(answer or '')} chars"
        ),
        tool_name="evaluate_answer",
        user_id=user_id,
        thread_id=thread_id,
    )
    log_event(
        "ACTIVITY_ANSWER_RECEIVED",
        message=(
            f"Answer received | {subject}/{topic} | "
            f"{len(answer or '')} chars"
        ),
        user_id=user_id,
        thread_id=thread_id,
        tool_name="evaluate_answer",
        extra={"subject": subject, "topic": topic},
    )

    activity = dict((state or {}).get("learning_activity") or {})
    activity_type = activity.get("activity_type", ACTIVITY_TYPE_EXERCISE)

    section = _find_section(subject, topic)
    if section is None:
        log_event(
            "TOOL_ERROR",
            level="WARNING",
            message=(
                f"evaluate_answer: topic '{topic}' introuvable "
                f"pour '{subject}'"
            ),
            tool_name="evaluate_answer",
            user_id=user_id,
            thread_id=thread_id,
        )
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            f"Impossible d'évaluer : le topic "
                            f"'{topic}' de '{subject}' n'a pas de "
                            "section knowledge. Évalue avec ton "
                            "propre jugement de tuteur."
                        ),
                        tool_call_id=tool_call_id or "",
                    )
                ]
            }
        )

    content_tokens = _content_tokens(section["content"])
    answer_tokens = _content_tokens(answer or "")
    key_terms = _key_terms(section["content"], max_terms=6)

    # Couverture des termes-clés
    covered = [t for t in key_terms if t in answer_tokens]
    missing = [t for t in key_terms if t not in answer_tokens]
    coverage = len(covered) / max(1, len(key_terms))

    # Richesse : tokens de cours présents dans la réponse
    overlap = content_tokens & answer_tokens
    richness = (
        len(overlap) / min(20, len(content_tokens))
        if content_tokens
        else 0.0
    )

    score = round(0.7 * coverage + 0.3 * min(1.0, richness), 2)

    # Appréciation formative (≠ note : guidance) + guidance §11/§13
    if score >= 0.75:
        verdict = "Très bonne réponse"
        advice = (
            "Félicite l'étudiant, MAIS vérifie la compréhension "
            "réelle AVANT d'enchaîner : appelle assess_understanding("
            f"subject='{subject}', topic='{section['topic']}', "
            "response=<ce que l'étudiant vient d'écrire>) et pose une "
            "question de reformulation (ex : « explique-moi pourquoi "
            "… »). Ne donne pas la question suivante tout de suite."
        )
        new_status = ACTIVITY_CHECKING_UNDERSTANDING
    elif score >= 0.4:
        verdict = "Réponse partielle"
        advice = (
            "Reconnais ce qui est juste, puis demande de développer "
            "les points manquants. Si l'étudiant bloque : "
            f"give_hint(subject='{subject}', "
            f"topic='{section['topic']}', level=0)."
        )
        new_status = ACTIVITY_WAITING_RETRY
    else:
        verdict = "Réponse insuffisante"
        advice = (
            "Reprends doucement : donne un indice avec "
            f"give_hint (subject='{subject}', "
            f"topic='{section['topic']}', level=0) et laisse "
            "l'étudiant réessayer — ne résous pas à sa place."
        )
        new_status = ACTIVITY_WAITING_RETRY

    # ---- Mise à jour de l'activité (attempts, score, status) ----
    if activity:
        activity["attempts"] = activity.get("attempts", 0) + 1
        activity["status"] = new_status
        activity["awaiting_answer"] = False
        activity["last_evaluation"] = {
            "score": score,
            "verdict": verdict,
            "covered": covered,
            "missing": missing,
        }

    result = (
        f"ÉVALUATION — {subject} / {section['topic']} "
        f"(source : {section['source']})\n\n"
        f"Score de couverture : {score * 100:.0f}% — {verdict}\n"
        f"Termes-clés couverts : "
        f"{', '.join(covered) if covered else 'aucun'}\n"
        f"Termes manquants : "
        f"{', '.join(missing) if missing else 'aucun'}\n\n"
        f"Prochaine étape pédagogique : {advice}"
    )

    log_event(
        "ACTIVITY_EVALUATED",
        message=(
            f"Answer evaluated | {subject}/{section['topic']} | "
            f"score={score} | verdict={verdict}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        tool_name="evaluate_answer",
        extra={
            "subject": subject,
            "topic": section["topic"],
            "score": score,
            "verdict": verdict,
        },
    )

    # ---- V6 : l'évaluation EST une observation pédagogique (§13) ----
    # Pipeline natif Exercise → Evaluation → LearningObservation →
    # Profile. Déterministe : le profil learning est mis à jour à
    # CHAQUE vraie évaluation, sans dépendre d'un second appel de
    # tool par le LLM. Le topic de section (ex: _intro, definition)
    # est RÉSOLU vers un topic Registry (ex: functions) — sinon
    # l'observation est rejetée (§18), jamais de topic inventé.
    # Un échec d'écriture ne bloque JAMAIS l'évaluation (§26).
    if user_id:
        try:
            from app.learning.learning_profile import (
                resolve_registry_topic,
                update_profile_from_observation,
            )
            from app.learning.schemas import LearningObservation

            registry_topic = resolve_registry_topic(
                subject, topic, source=section.get("source")
            )
            if registry_topic:
                update_profile_from_observation(
                    user_id,
                    LearningObservation(
                        subject=subject,
                        topic=registry_topic,
                        type="exercise",
                        score=score,
                        strengths=covered[:3],
                        weak_points=missing[:3],
                        confidence=0.8,
                    ),
                    thread_id=thread_id or "",
                )
        except Exception as exc:
            log_event(
                "LEARNING_PROFILE_UPDATE",
                level="WARNING",
                message=(
                    f"Auto-observation après evaluate_answer "
                    f"échouée (non bloquant) : {exc}"
                ),
                user_id=user_id,
                thread_id=thread_id,
                extra={
                    "operation": "learning_observation_auto",
                    "subject": subject,
                    "topic": section["topic"],
                },
            )

    update: dict = {
        "messages": [
            ToolMessage(content=result, tool_call_id=tool_call_id or "")
        ],
        "activity_log": [
            _activity_log_entry(
                "ACTIVITY_ANSWER_RECEIVED",
                new_status,
                f"answer evaluated: score={score} ({verdict})",
                0,
                activity_type,
            ),
            _activity_log_entry(
                "ACTIVITY_EVALUATED",
                new_status,
                f"score={score} | {verdict} | missing={missing}",
                0,
                activity_type,
            ),
        ],
    }
    if activity:
        update["learning_activity"] = activity

    return Command(update=update)


# ------------------------------------------------------------------
# INDICES PROGRESSIFS (§9, §21)
# ------------------------------------------------------------------


@tool
def give_hint(
    subject: str,
    topic: str,
    level: int = 0,
    state: Annotated[dict | None, InjectedState] = None,
    tool_call_id: Annotated[str | None, InjectedToolCallId] = None,
    config: RunnableConfig = None,
) -> Command:
    """Donne un indice PROGRESSIF sur un topic, sans révéler la
    solution complète, et track le niveau d'indice dans l'activité.

    HINT MODE : quand l'étudiant dit qu'il est bloqué, appelle ce tool
    avec level=0, transmets l'indice dans ta réponse, puis ATTENDS une
    nouvelle tentative. Si l'étudiant reste bloqué, rappelle avec
    level=1 puis level=2 — les niveaux sont PROGRESSIFS : ne saute
    jamais directement au niveau maximal.

    Niveaux d'indices construits depuis le contenu réel du cours :
      0 = orienter (quelle direction regarder)
      1 = préciser (le mécanisme clé impliqué)
      2 = presque la solution (point précis à formuler)

    Args:
        subject: id de la matière (ex: "python").
        topic: le topic (ex: "return").
        level: 0, 1 ou 2 (défaut 0 — le moins révélant).
    """
    user_id, thread_id = _thread_ids(config)
    log_event(
        "TOOL_CALL",
        message=(
            f"give_hint subject={subject} topic={topic} level={level}"
        ),
        tool_name="give_hint",
        user_id=user_id,
        thread_id=thread_id,
    )
    log_event(
        "ACTIVITY_HINT_REQUESTED",
        message=f"Hint requested | {subject}/{topic} | level={level}",
        user_id=user_id,
        thread_id=thread_id,
        tool_name="give_hint",
        extra={"subject": subject, "topic": topic, "level": level},
    )

    activity = dict((state or {}).get("learning_activity") or {})
    activity_type = activity.get("activity_type", ACTIVITY_TYPE_EXERCISE)

    section = _find_section(subject, topic)
    if section is None:
        from app.subjects.registry import get_subject

        cfg = get_subject(subject)
        available = ", ".join(_available_topics(subject)) or (
            ", ".join(cfg.topics) if cfg else "matière inconnue"
        )
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            f"Aucune section knowledge pour le topic "
                            f"'{topic}' de '{subject}'. Topics "
                            f"disponibles : {available}."
                        ),
                        tool_call_id=tool_call_id or "",
                    )
                ]
            }
        )

    terms = _key_terms(section["content"], max_terms=3)
    topic_name = section["topic"]
    src = section["source"]

    # Premier bloc de contenu = la définition de la section
    first_lines = [
        ln
        for ln in section["content"].splitlines()
        if ln.strip()
    ][:2]
    definition = " ".join(first_lines)

    # Progressivité des indices (§9) : on ne recule JAMAIS (un
    # étudiant qui a vu le niveau 1 ne redescend pas), et on
    # n'avance que d'UN niveau maximum par blocage — jamais de
    # saut direct à la solution.
    requested = max(0, min(2, int(level)))
    current = int(activity.get("hint_level", 0))
    if requested <= current:
        # re-demande au même niveau ou inférieur → niveau courant
        level = current
    else:
        # demande un niveau supérieur → au plus +1
        level = min(current + 1, 2)
    level = max(0, min(2, level))

    if level == 0:
        hint = (
            f"INDICE 1 (orientation) — {topic_name}\n"
            f"Repense à ce que fait {topic_name} : {terms[0]} "
            f"est au cœur du mécanisme. Relis d'abord ce que tu "
            f"sais de {terms[0]}."
        )
    elif level == 1:
        hint = (
            f"INDICE 2 (précision) — {topic_name}\n"
            f"Le point clé : {definition[:200]}… "
            f"Concentre-toi sur le rôle de {terms[0]}"
            + (f" et {terms[1]}" if len(terms) > 1 else "")
            + "."
        )
    else:
        hint = (
            f"INDICE 3 (presque la solution) — {topic_name}\n"
            f"Formule ta réponse autour de : "
            f"{', '.join(terms)}. "
            f"Le cours dit précisément : « {definition[:300]} »"
        )

    hint += f"\n(source : {src} — contenu du cours, pas inventé)"
    hint += (
        "\n\nTRANSMISSION : reformule cet indice à l'étudiant avec tes "
        "mots de tuteur, puis ATTENDS sa nouvelle tentative. Ne donne "
        "pas la solution complète tant qu'il n'a pas réessayé."
    )

    # ---- Hint mode : l'activité attend un retry ----
    if activity:
        activity["hint_level"] = level
        activity["status"] = ACTIVITY_WAITING_RETRY
        activity["awaiting_answer"] = True

    log_event(
        "TOOL_RESULT",
        message=f"give_hint level={level} | source={src}",
        tool_name="give_hint",
        user_id=user_id,
        thread_id=thread_id,
    )

    update: dict = {
        "messages": [
            ToolMessage(content=hint, tool_call_id=tool_call_id or "")
        ],
        "activity_log": [
            _activity_log_entry(
                "ACTIVITY_HINT_REQUESTED",
                ACTIVITY_WAITING_RETRY,
                f"hint level={level} on {subject}/{topic}",
                level,
                activity_type,
            )
        ],
    }
    if activity:
        update["learning_activity"] = activity

    return Command(update=update)


# ------------------------------------------------------------------
# QUIZ CONVERSATIONNEL (§17-§21)
# ------------------------------------------------------------------


@tool
def create_quiz(
    subject: str,
    topic: str,
    num_questions: int = 3,
    state: Annotated[dict | None, InjectedState] = None,
    tool_call_id: Annotated[str | None, InjectedToolCallId] = None,
    config: RunnableConfig = None,
) -> Command:
    """Démarre un quiz INTERACTIF sur un topic : les questions sont
    posées UNE PAR UNE, jamais toutes en même temps.

    Le tool ouvre l'activité quiz et fournit la PREMIÈRE question.
    La question suivante n'est livrée qu'après évaluation de la
    réponse courante : utilise evaluate_answer sur la réponse de
    l'étudiant, fais ton feedback conversationnel (indice si
    besoin), puis rappelle create_quiz avec next_question=true
    pour obtenir la question suivante.

    Args:
        subject: id de la matière (ex: "python", "biology").
        topic: le topic du quiz (ex: "return", "membrane").
        num_questions: nombre de questions souhaitées (1-5, défaut 3).
    """
    return _quiz_tool_impl(
        subject,
        topic,
        num_questions,
        next_question=False,
        state=state,
        tool_call_id=tool_call_id,
        config=config,
    )


@tool
def create_quiz_next(
    subject: str,
    topic: str,
    num_questions: int = 3,
    next_question: bool = False,
    state: Annotated[dict | None, InjectedState] = None,
    tool_call_id: Annotated[str | None, InjectedToolCallId] = None,
    config: RunnableConfig = None,
) -> Command:
    """Passe à la question suivante du quiz interactif en cours sur CE
    thread.

    À appeler APRÈS avoir évalué la réponse de l'étudiant à la question
    courante (evaluate_answer) et fait ton feedback. Retourne :
      - la question suivante (index+1/total) s'il en reste ;
      - le résultat final (score, bilan) si le quiz est terminé.

    Args:
        subject: id de la matière (doit être celui du quiz en cours).
        topic: le topic du quiz en cours.
        next_question: toujours true pour ce tool.
        num_questions: ignoré ici (le quiz existe déjà dans le state).
    """
    return _quiz_tool_impl(
        subject,
        topic,
        num_questions,
        next_question=True,
        state=state,
        tool_call_id=tool_call_id,
        config=config,
    )


def _quiz_tool_impl(
    subject: str,
    topic: str,
    num_questions: int,
    next_question: bool,
    state: dict | None,
    tool_call_id: str | None,
    config: RunnableConfig | None,
) -> Command:
    """Implémentation partagée create_quiz / create_quiz_next."""
    user_id, thread_id = _thread_ids(config)

    activity = dict((state or {}).get("learning_activity") or {})

    # ---------- Mode : question suivante ----------
    if next_question:
        if (
            not activity
            or activity.get("activity_type") != ACTIVITY_TYPE_QUIZ
        ):
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=(
                                "Aucun quiz en cours dans ce thread. "
                                "Démarre d'abord un quiz avec "
                                f"create_quiz(subject='{subject}', "
                                f"topic='{topic}')."
                            ),
                            tool_call_id=tool_call_id or "",
                        )
                    ]
                }
            )

        idx = int(activity.get("current_index", 0))
        total = int(activity.get("total_questions", 0))
        nxt = idx + 1

        if nxt >= total:
            # ---- Quiz terminé ----
            score = float(activity.get("score", 0.0))
            activity["status"] = ACTIVITY_COMPLETED
            activity["awaiting_answer"] = False
            log_event(
                "QUIZ_COMPLETED",
                message=(
                    f"Quiz completed | {activity.get('subject')}/"
                    f"{activity.get('topic')} | score={score}"
                ),
                user_id=user_id,
                thread_id=thread_id,
                tool_name="create_quiz",
                extra={
                    "activity_id": activity.get("activity_id", ""),
                    "score": score,
                },
            )
            final = (
                f"QUIZ TERMINÉ — {activity.get('subject')}/"
                f"{activity.get('topic')}\n\n"
                f"Questions répondues : {total}\n"
                f"Score final : {score:.2f}\n\n"
                "Fais le bilan conversationnel : ce qui est acquis, "
                "ce qui mérite révision. Puis propose une suite "
                "(autre topic, ou exercice d'approfondissement avec "
                "create_exercise)."
            )
            return Command(
                update={
                    "learning_activity": activity,
                    "activity_log": [
                        _activity_log_entry(
                            "QUIZ_COMPLETED",
                            ACTIVITY_COMPLETED,
                            f"quiz done | score={score}",
                            0,
                            ACTIVITY_TYPE_QUIZ,
                        )
                    ],
                    "messages": [
                        ToolMessage(
                            content=final,
                            tool_call_id=tool_call_id or "",
                        )
                    ],
                }
            )

        # ---- Il reste des questions ----
        q = activity["questions"][nxt]
        activity["current_index"] = nxt
        activity["question_index"] = nxt
        activity["status"] = ACTIVITY_WAITING_ANSWER
        activity["awaiting_answer"] = True
        activity["hint_level"] = 0

        log_event(
            "QUIZ_QUESTION",
            message=(
                f"Quiz question {nxt + 1}/{total} | "
                f"{activity.get('subject')}/{activity.get('topic')}"
            ),
            user_id=user_id,
            thread_id=thread_id,
            tool_name="create_quiz",
            extra={
                "activity_id": activity.get("activity_id", ""),
                "index": nxt,
                "total": total,
            },
        )

        content = (
            f"QUESTION {nxt + 1}/{total} — "
            f"{activity.get('subject')}/{activity.get('topic')}\n\n"
            f"{q['question']}\n\n"
            "Pose-la telle quelle à l'étudiant et ATTENDS sa "
            "réponse. Après réponse : evaluate_answer, feedback "
            "conversationnel (indice si besoin), puis "
            "create_quiz_next(next_question=true)."
        )
        return Command(
            update={
                "learning_activity": activity,
                "activity_log": [
                    _activity_log_entry(
                        "QUIZ_QUESTION",
                        ACTIVITY_WAITING_ANSWER,
                        f"question {nxt + 1}/{total}",
                        0,
                        ACTIVITY_TYPE_QUIZ,
                    )
                ],
                "messages": [
                    ToolMessage(
                        content=content,
                        tool_call_id=tool_call_id or "",
                    )
                ],
            }
        )

    # ---------- Mode : démarrage ----------
    log_event(
        "TOOL_CALL",
        message=(
            f"create_quiz subject={subject} topic={topic} "
            f"num_questions={num_questions}"
        ),
        tool_name="create_quiz",
        user_id=user_id,
        thread_id=thread_id,
    )

    section = _find_section(subject, topic)
    if section is None:
        from app.subjects.registry import get_subject

        cfg = get_subject(subject)
        available = ", ".join(_available_topics(subject)) or (
            ", ".join(cfg.topics) if cfg else "matière inconnue"
        )
        log_event(
            "TOOL_ERROR",
            level="WARNING",
            message=(
                f"create_quiz: topic '{topic}' introuvable pour "
                f"'{subject}'"
            ),
            tool_name="create_quiz",
            user_id=user_id,
            thread_id=thread_id,
        )
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            f"Aucune section knowledge pour le topic "
                            f"'{topic}' de '{subject}'. Topics "
                            f"disponibles : {available}. Propose un "
                            "choix — n'invente pas de quiz."
                        ),
                        tool_call_id=tool_call_id or "",
                    )
                ]
            }
        )

    # Construit les questions depuis le CONTENU RÉEL de la section
    # (et ses topics voisins du même subject pour varier) — jamais
    # inventées.
    num = max(1, min(5, int(num_questions or 3)))
    questions = _build_quiz_questions(subject, section, num)

    activity = {
        "activity_id": new_activity_id(subject, topic),
        "activity_type": ACTIVITY_TYPE_QUIZ,
        "subject": subject,
        "topic": section["topic"],
        "status": ACTIVITY_WAITING_ANSWER,
        "question": questions[0]["question"],
        "expected_response_type": questions[0].get(
            "expected_response_type", RESPONSE_TYPE_SHORT_ANSWER
        ),
        "source": section["source"],
        "hint_level": 0,
        "attempts": 0,
        "awaiting_answer": True,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "questions": questions,
        "total_questions": len(questions),
        "current_index": 0,
        "question_index": 0,
        "score": 0.0,
    }

    log_event(
        "QUIZ_STARTED",
        message=(
            f"Quiz started | {subject}/{section['topic']} | "
            f"questions={len(questions)}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        tool_name="create_quiz",
        extra={
            "activity_id": activity["activity_id"],
            "subject": subject,
            "topic": section["topic"],
            "total_questions": len(questions),
        },
    )
    log_event(
        "QUIZ_QUESTION",
        message=f"Quiz question 1/{len(questions)}",
        user_id=user_id,
        thread_id=thread_id,
        tool_name="create_quiz",
        extra={"index": 0, "total": len(questions)},
    )

    content = (
        f"QUIZ OUVERT — {subject}/{section['topic']} "
        f"({len(questions)} questions, source : {section['source']})\n\n"
        f"QUESTION 1/{len(questions)} :\n"
        f"{questions[0]['question']}\n\n"
        "Pose CETTE question à l'étudiant et ATTENDS sa réponse. "
        "Ne dévoile jamais les questions suivantes. Après chaque "
        "réponse : evaluate_answer → feedback conversationnel → "
        "create_quiz_next(next_question=true)."
    )

    return Command(
        update={
            "learning_activity": activity,
            "activity_log": [
                _activity_log_entry(
                    "QUIZ_STARTED",
                    ACTIVITY_WAITING_ANSWER,
                    f"quiz {subject}/{section['topic']} "
                    f"({len(questions)} questions)",
                    0,
                    ACTIVITY_TYPE_QUIZ,
                ),
                _activity_log_entry(
                    "QUIZ_QUESTION",
                    ACTIVITY_WAITING_ANSWER,
                    "question 1/" + str(len(questions)),
                    0,
                    ACTIVITY_TYPE_QUIZ,
                ),
            ],
            "messages": [
                ToolMessage(content=content, tool_call_id=tool_call_id or "")
            ],
        }
    )


def _build_quiz_questions(
    subject: str, section: dict, num: int
) -> list[dict]:
    """Construit num questions de quiz depuis les sections knowledge
    réelles du subject (section demandée + voisines). Chaque question
    est dérivée du contenu du cours — jamais inventée."""
    from app.subjects.registry import get_subject as _gs

    cfg = _gs(subject)
    sections: list[dict] = [section]
    if cfg:
        for t in _available_topics(subject):
            if len(sections) >= num:
                break
            if _strip_accents(t.lower()) == _strip_accents(
                section["topic"].lower()
            ):
                continue
            other = _find_section(subject, t)
            if other:
                sections.append(other)

    questions: list[dict] = []
    for i, sec in enumerate(sections[:num]):
        terms = _key_terms(sec["content"], max_terms=3)
        ask_terms = ", ".join(terms[:2]) if terms else sec["topic"]
        questions.append(
            {
                "question": (
                    f"Question {i + 1} ({sec['topic']}) : "
                    f"explique avec tes mots ce qu'est "
                    f"« {sec['topic']} » dans {subject}, en "
                    f"mentionnant {ask_terms}."
                ),
                "topic": sec["topic"],
                "source": sec["source"],
                "expected": terms,
                "expected_response_type": (
                    RESPONSE_TYPE_CODE
                    if _is_code_subject(subject)
                    else RESPONSE_TYPE_SHORT_ANSWER
                ),
            }
        )
    return questions


# ------------------------------------------------------------------
# VÉRIFICATION DE COMPRÉHENSION (§11-§13)
# ------------------------------------------------------------------


@tool
def assess_understanding(
    subject: str,
    topic: str,
    response: str,
    state: Annotated[dict | None, InjectedState] = None,
    tool_call_id: Annotated[str | None, InjectedToolCallId] = None,
    config: RunnableConfig = None,
) -> Command:
    """Évalue la COMPRÉHENSION IMMÉDIATE d'un étudiant sur un topic,
    à partir de sa reformulation ou explication (≠ réponse correcte).

    À utiliser après une réponse correcte (evaluate_answer score
    élevé) pour distinguer « réponse correcte » de « compréhension
    réelle » : demande à l'étudiant d'expliquer avec ses mots, puis
    passe sa réponse à ce tool.

    Retour structuré :
      status : understood | partial | unclear | not_understood
      confidence, understood[] (points compris), unclear[] (points
      flous), recommended_action (ask_followup | give_hint |
      conclude | re_explain)

    IMPORTANT : ce résultat est une OBSERVATION locale au thread —
    ce n'est PAS un mastery et n'écrit RIEN dans le Learning Profile.

    Args:
        subject: id de la matière (ex: "python").
        topic: le topic vérifié (ex: "return").
        response: l'explication de l'étudiant, mot pour mot.
    """
    user_id, thread_id = _thread_ids(config)
    log_event(
        "TOOL_CALL",
        message=(
            f"assess_understanding subject={subject} topic={topic} "
            f"response={len(response or '')} chars"
        ),
        tool_name="assess_understanding",
        user_id=user_id,
        thread_id=thread_id,
    )

    activity = dict((state or {}).get("learning_activity") or {})
    activity_type = activity.get("activity_type", "")

    section = _find_section(subject, topic)
    if section is None:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            f"Impossible d'évaluer la compréhension : "
                            f"pas de section knowledge pour "
                            f"'{topic}' de '{subject}'. Utilise ton "
                            "jugement de tuteur."
                        ),
                        tool_call_id=tool_call_id or "",
                    )
                ]
            }
        )

    key_terms = _key_terms(section["content"], max_terms=6)
    resp_tokens = _content_tokens(response or "")

    understood = [t for t in key_terms if t in resp_tokens]
    unclear = [t for t in key_terms if t not in resp_tokens]
    coverage = len(understood) / max(1, len(key_terms))

    # Longueur minimale : une vraie explication ne fait pas 3 mots
    n_words = len((response or "").split())
    if coverage >= 0.7 and n_words >= 15:
        status = "understood"
        confidence = round(0.6 + 0.3 * coverage, 2)
        recommended = "conclude"
    elif coverage >= 0.4 or n_words >= 15:
        status = "partial"
        confidence = round(0.35 + 0.35 * coverage, 2)
        recommended = "ask_followup"
    elif n_words >= 5:
        status = "unclear"
        confidence = round(0.2 + 0.25 * coverage, 2)
        recommended = "give_hint"
    else:
        status = "not_understood"
        confidence = round(0.1 + 0.15 * coverage, 2)
        recommended = "re_explain"

    assessment: dict = {
        "status": status,
        "confidence": confidence,
        "understood": understood,
        "unclear": unclear,
        "recommended_action": recommended,
        "subject": subject,
        "topic": section["topic"],
    }

    guidance = {
        "understood": (
            "Compréhension confirmée. Conclus l'activité avec un "
            "feedback positif, propose la suite (question suivante, "
            "autre topic, ou exercice)."
        ),
        "partial": (
            "Compréhension PARTIELLE : demande un follow-up ciblé sur "
            "les points flous ("
            + (", ".join(unclear) if unclear else "reformule la notion centrale")
            + "). Attends la reformulation de l'étudiant avant de "
            "conclure."
        ),
        "unclear": (
            "Explication floue : redonne un indice orientation avec "
            f"give_hint(subject='{subject}', topic='{topic}', "
            "level=0) et laisse l'étudiant reformuler."
        ),
        "not_understood": (
            "Pas de compréhension détectée : réexplique le concept "
            "différemment (autre angle, exemple concret), puis "
            "redemande une reformulation."
        ),
    }[status]

    # Mise à jour de l'activité : compréhension vérifiée
    if activity:
        activity["understanding"] = assessment
        if status == "understood":
            activity["status"] = ACTIVITY_COMPLETED
            activity["awaiting_answer"] = False
        else:
            activity["status"] = ACTIVITY_CHECKING_UNDERSTANDING

    result = (
        f"COMPRÉHENSION — {subject} / {section['topic']}\n\n"
        f"Status : {status} (confiance {confidence})\n"
        f"Points compris : "
        f"{', '.join(understood) if understood else 'aucun'}\n"
        f"Points flous : {', '.join(unclear) if unclear else 'aucun'}\n"
        f"Action recommandée : {recommended}\n\n"
        f"Guidance : {guidance}\n\n"
        "(observation locale — aucune écriture dans un profil "
        "d'apprentissage)"
    )

    log_event(
        "ACTIVITY_UNDERSTANDING_ASSESSED",
        message=(
            f"Understanding assessed | {subject}/"
            f"{section['topic']} | status={status} | "
            f"confidence={confidence}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        tool_name="assess_understanding",
        extra={**assessment},
    )

    update: dict = {
        "messages": [
            ToolMessage(content=result, tool_call_id=tool_call_id or "")
        ],
        "activity_log": [
            _activity_log_entry(
                "ACTIVITY_UNDERSTANDING_ASSESSED",
                assessment.get("status", ""),
                f"understanding={status} confidence={confidence}",
                0,
                activity_type,
            )
        ],
    }
    if activity:
        update["learning_activity"] = activity

    return Command(update=update)


# ------------------------------------------------------------------
# RÉVISION (§36)
# ------------------------------------------------------------------


@tool
def propose_review(
    subject: str,
    state: Annotated[dict | None, InjectedState] = None,
    tool_call_id: Annotated[str | None, InjectedToolCallId] = None,
    config: RunnableConfig = None,
) -> Command:
    """Propose un plan de révision pour une matière, basé sur les
    topics RÉELLEMENT disponibles dans la base knowledge (jamais
    inventés) et sur l'état du quiz/exercice en cours.

    Utilise-le quand l'étudiant demande « qu'est-ce que je devrais
    réviser ? », après un quiz raté, ou pour conclure une session.

    Args:
        subject: id de la matière (ex: "python").
    """
    user_id, thread_id = _thread_ids(config)
    log_event(
        "TOOL_CALL",
        message=f"propose_review subject={subject}",
        tool_name="propose_review",
        user_id=user_id,
        thread_id=thread_id,
    )

    activity = dict((state or {}).get("learning_activity") or {})
    activity_type = activity.get("activity_type", "")

    topics = _available_topics(subject)
    if not topics:
        from app.subjects.registry import get_subject

        cfg = get_subject(subject)
        available = (
            ", ".join(cfg.topics) if cfg else "matière inconnue"
        )
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            f"Aucune base knowledge disponible pour "
                            f"'{subject}'. Topics déclarés : "
                            f"{available}. Signale-le à l'étudiant."
                        ),
                        tool_call_id=tool_call_id or "",
                    )
                ]
            }
        )

    # Si un quiz est en cours, ses données enrichissent la révision
    review_lines: list[str] = []
    if (
        activity
        and activity.get("subject") == subject
        and activity.get("last_evaluation")
    ):
        ev = activity["last_evaluation"]
        missing = ev.get("missing") or []
        if missing:
            review_lines.append(
                f"- {activity.get('topic')} : points à retravailler "
                f"— {', '.join(missing)}"
            )
        if activity.get("hint_level", 0) >= 2:
            review_lines.append(
                f"- {activity.get('topic')} : indices poussés "
                "utilisés — notion fragile, à reprendre à la base"
            )

    for t in topics:
        if activity and activity.get("topic") == t:
            continue
        review_lines.append(f"- {t}")

    content = (
        f"PLAN DE RÉVISION — {subject}\n\n"
        f"Topics disponibles dans la base du cours :\n"
        + "\n".join(review_lines)
        + "\n\nPrésente ce plan à l'étudiant sous forme de choix "
        "conversationnel : quel topic veut-il réviser en premier ? "
        "Ne démarre pas l'exercice automatiquement."
    )

    log_event(
        "TOOL_RESULT",
        message=(
            f"propose_review | {subject} | topics={len(topics)}"
        ),
        tool_name="propose_review",
        user_id=user_id,
        thread_id=thread_id,
    )

    return Command(
        update={
            "activity_log": [
                _activity_log_entry(
                    "ACTIVITY_REVIEW_PROPOSED",
                    "",
                    f"review plan for {subject}",
                    0,
                    activity_type,
                )
            ],
            "messages": [
                ToolMessage(
                    content=content, tool_call_id=tool_call_id or ""
                )
            ],
        }
    )


pedagogical_tools = [
    create_exercise,
    evaluate_answer,
    give_hint,
    create_quiz,
    create_quiz_next,
    assess_understanding,
    propose_review,
]
