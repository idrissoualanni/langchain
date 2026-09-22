# Research Subgraph — PLANNER (V1, DÉTERMINISTE, aucun LLM).
#
# build_research_plan : décompose une question en un plan de requêtes
# web. Chaque tâche : {query, focus, subject, topic, language}. Le
# nombre de requêtes est BORNÉ par max_queries (défaut 4 ≡
# max_iterations) → la boucle LangGraph qui consomme ces tâches est
# structurellement bornée (Jamais de while illimité).
#
# Entrée        →   Plan borné de requêtes
#   question        →   [{query, focus, ...} × n ≤ max_queries]
from __future__ import annotations

from app.services.context.query_norm import normalize_query

# Nombre de requêtes par défaut d'un plan (= borne de la boucle).
DEFAULT_MAX_QUERIES = 4

# Stop-words FR/EN courts ou structuraux — non discriminants pour une
# requête web.
_STOP = {
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "en",
    "au", "aux", "d", "l", "the", "a", "an", "of", "and", "in", "is",
    "are", "pour", "quoi", "comment", "est", "que", "qui", "ce", "c",
    "je", "tu", "il", "elle", "nous", "vous", "sur", "avec", "dans",
    "par", "moi", "toi", "plus", "mon", "ma", "mes", "ton", "ta",
    "tes", "explique", "expliquer", "expliquez",
}

# Variantes de focus : chaque requête explore une facette différente
# (définition, exemples, comparaison, causes/effets).
_FOCUS_VARIANTS = (
    (("definition",), "definition"),
    (("exemples", "examples"), "examples"),
    (("comparaison", "avantages", "inconvenients"), "comparaison"),
    (("causes", "effets"), "causes"),
)


def _significant_tokens(question: str) -> list[str]:
    """Tokens signifiants de la question (dédupliqués, bornés à 6)."""
    norm = normalize_query(question or "")
    seen: set[str] = set()
    out: list[str] = []
    for tok in norm.split():
        if len(tok) >= 4 and tok not in _STOP and tok not in seen:
            seen.add(tok)
            out.append(tok)
        if len(out) >= 6:
            break
    return out


def build_research_plan(
    question: str,
    objective: str = "",
    subject: str | None = None,
    topic: str | None = None,
    language: str = "fr",
    max_queries: int = DEFAULT_MAX_QUERIES,
    plan_override: list | None = None,
) -> list[dict]:
    """Plan de recherche borné : list[dict] {query, focus, ...}.

    DÉTERMINISTE : entrée identique → plan identique (aucun LLM).
    `max_queries` borne la taille du plan → borne la boucle du graphe.

    `plan_override` : liste optionnelle de chaînes de requêtes fournie
    via le payload (ex. par un orchestrateur) — utilisées telles
    quelles (toujours bornées par `max_queries` en aval du graphe).
    """
    if plan_override:
        tasks: list[dict] = []
        for raw in plan_override:
            q = str(raw or "").strip()
            if q:
                tasks.append(
                    {
                        "query": q,
                        "focus": "general",
                        "subject": subject,
                        "topic": topic,
                        "language": language or "fr",
                    }
                )
        return tasks

    q = str(question or "").strip().rstrip("? ").strip()
    if not q:
        return []

    n = max(1, int(max_queries or DEFAULT_MAX_QUERIES))
    base = q[:140]

    tasks = [
        {
            "query": base,
            "focus": "general",
            "subject": subject,
            "topic": topic,
            "language": language or "fr",
        }
    ]
    for keywords, focus in _FOCUS_VARIANTS:
        if len(tasks) >= n:
            break
        suffix = " ".join(keywords)
        tasks.append(
            {
                "query": f"{base} {suffix}".strip(),
                "focus": focus,
                "subject": subject,
                "topic": topic,
                "language": language or "fr",
            }
        )
    return tasks[:n]


__all__ = ["build_research_plan", "DEFAULT_MAX_QUERIES"]