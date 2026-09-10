# Tools pédagogiques communs V4.1 — VRAIES implémentations, pas des
# simulations. Branchés sur la base knowledge réelle (app/knowledge/):
# chaque exercice/évaluation/indice est généré depuis le CONTENU
# du cours, jamais inventé.
#
#   create_exercise(subject, topic) → exercice structuré Q/R
#   evaluate_answer(subject, topic, answer) → scoring couverture
#   give_hint(subject, topic, level) → indices progressifs
import re
import unicodedata

from langchain_core.tools import tool

from app.context.knowledge_retriever import (
    KNOWLEDGE_DIR,
    _split_sections,
    _tokens,
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


def _find_section(subject: str, topic: str) -> dict | None:
    """Cherche la section knowledge (source + topic + content) d'un
    topic donné d'une matière. Retour None si introuvable."""
    from app.subjects.registry import get_subject

    cfg = get_subject(subject)
    if cfg is None:
        return None

    topic_norm = _strip_accents((topic or "").lower())
    for src in cfg.knowledge.get("sources", []):
        path = KNOWLEDGE_DIR / f"{src}.md"
        if not path.exists():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for sec_topic, sec_content in _split_sections(content):
            if _strip_accents(sec_topic.lower()) == topic_norm:
                return {
                    "source": f"{path.parent.name}/{path.stem}",
                    "topic": sec_topic,
                    "content": sec_content,
                }
    return None


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


@tool
def create_exercise(subject: str, topic: str) -> str:
    """Génère un exercice d'entraînement réel sur un topic d'une matière.

    L'exercice est construit depuis la base de connaissances du cours
    (contenu vérifié, pas inventé) : question ouverte + rappel du
    contexte + critères de réussite.

    Args:
        subject: id de la matière (ex: "python", "biology",
            "mathematics", "computer_networks").
        topic: le topic précis (ex: "return", "membrane", "equations",
            "osi"). Utilise give_hint avec level=0 pour découvrir
            les topics disponibles.
    """
    log_event(
        "TOOL_CALL",
        message=f"create_exercise subject={subject} topic={topic}",
        tool_name="create_exercise",
    )

    section = _find_section(subject, topic)
    if section is None:
        # Aucune invention : liste les topics réellement disponibles
        from app.subjects.registry import get_subject

        cfg = get_subject(subject)
        available = (
            ", ".join(cfg.topics)
            if cfg
            else "matière inconnue"
        )
        log_event(
            "TOOL_ERROR",
            level="WARNING",
            message=(
                f"create_exercise: topic '{topic}' introuvable "
                f"pour '{subject}'"
            ),
            tool_name="create_exercise",
        )
        return (
            f"Aucune section knowledge trouvée pour le topic "
            f"'{topic}' de '{subject}'. "
            f"Topics disponibles : {available}. "
            "Propose plutôt un des topics listés."
        )

    terms = _key_terms(section["content"], max_terms=4)
    src = section["source"]

    exercise = (
        f"EXERCICE — {subject} / {section['topic']}\n"
        f"(source : {src})\n\n"
        f"Question :\n"
        f"Explique avec tes mots ce qu'est « {section['topic']} » "
        f"dans le contexte de {subject}, en mentionnant : "
        f"{', '.join(terms[:3])}.\n\n"
        f"Pour bien répondre :\n"
        f"- définis {section['topic']} précisément ;\n"
        f"- utilise chacun des termes suivants : "
        f"{', '.join(terms)} ;\n"
        f"- donne un exemple concret.\n\n"
        f"Quand l'étudiant a répondu, évalue sa réponse avec "
        f"evaluate_answer (subject='{subject}', "
        f"topic='{section['topic']}')."
    )

    log_event(
        "TOOL_RESULT",
        message=(
            f"create_exercise ok | source={src} | "
            f"terms={terms}"
        ),
        tool_name="create_exercise",
    )
    return exercise


@tool
def evaluate_answer(
    subject: str, topic: str, answer: str
) -> str:
    """Évalue la réponse d'un étudiant sur un topic, par couverture
    du contenu réel du cours.

    Scoring déterministe : proportion des termes-clés de la section
    knowledge couverts par la réponse + retour formatif (termes
    manquants, prochaine étape). PAS une simulation : le score vient
    de la comparaison réponse ↔ base de cours.

    Args:
        subject: id de la matière (ex: "python").
        topic: le topic évalué (ex: "return").
        answer: la réponse de l'étudiant, mot pour mot.
    """
    log_event(
        "TOOL_CALL",
        message=(
            f"evaluate_answer subject={subject} topic={topic} "
            f"answer={len(answer or '')} chars"
        ),
        tool_name="evaluate_answer",
    )

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
        )
        return (
            f"Impossible d'évaluer : le topic '{topic}' de "
            f"'{subject}' n'a pas de section knowledge. "
            "Évalue avec ton propre jugement de tuteur."
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

    # Appréciation formative (≠ note : guidance)
    if score >= 0.75:
        verdict = "Très bonne réponse"
        advice = (
            "Félicite l'étudiant et propose d'approfondir "
            "un topic voisin."
        )
    elif score >= 0.4:
        verdict = "Réponse partielle"
        advice = (
            "Reconnais ce qui est juste, puis demande de "
            "développer les points manquants."
        )
    else:
        verdict = "Réponse insuffisante"
        advice = (
            "Reprends doucement : donne un indice avec "
            f"give_hint (subject='{subject}', "
            f"topic='{section['topic']}')."
        )

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
        "TOOL_RESULT",
        message=(
            f"evaluate_answer | score={score} | covered="
            f"{len(covered)} | missing={len(missing)}"
        ),
        tool_name="evaluate_answer",
    )
    return result


@tool
def give_hint(
    subject: str, topic: str, level: int = 0
) -> str:
    """Donne un indice PROGRESSIF sur un topic, sans révéler la
    solution complète.

    Niveaux d'indices construits depuis le contenu réel du cours :
      0 = orienter (quelle direction regarder)
      1 = préciser (le mécanisme clé impliqué)
      2 = presque la solution (point précis à formuler)

    Args:
        subject: id de la matière (ex: "python").
        topic: le topic (ex: "return").
        level: 0, 1 ou 2 (défaut 0 — le moins révélant).
    """
    log_event(
        "TOOL_CALL",
        message=(
            f"give_hint subject={subject} topic={topic} "
            f"level={level}"
        ),
        tool_name="give_hint",
    )

    section = _find_section(subject, topic)
    if section is None:
        from app.subjects.registry import get_subject

        cfg = get_subject(subject)
        available = (
            ", ".join(cfg.topics) if cfg else "matière inconnue"
        )
        return (
            f"Aucune section knowledge pour le topic '{topic}' de "
            f"'{subject}'. Topics disponibles : {available}."
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

    level = max(0, min(2, int(level)))
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

    log_event(
        "TOOL_RESULT",
        message=f"give_hint level={level} | source={src}",
        tool_name="give_hint",
    )
    return hint


pedagogical_tools = [
    create_exercise,
    evaluate_answer,
    give_hint,
]
