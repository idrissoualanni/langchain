# Research Subgraph — ResearchState typé (état INTERNE du subgraph).
#
# L'état est entièrement contenu au subgraph : jamais exposé au Main
# Graph (cf. §5 — les subgraphs spécialisés n'exposent que leur sortie
# structurée). Entrée (query/question/payload) et sortie
# (workflow_result) transitent par des canaux partagés, cohérents avec
# le pattern du ProblemSubgraph (problem/state.py).
#
# Boucle bornée : `plan` contient la liste des requêtes web à exécuter
# (≤ max_iterations), `tasks` est la file résiduelle consommée par le
# node research ; `iteration` avance d'un cran par tâche consommée. La
# boucle LangGraph s'arrête quand tasks est vide OU iteration >=
# max_iterations (borné par construction — aucun while illimité).
from typing import TypedDict


class ResearchState(TypedDict, total=False):
    """État interne du ResearchSubgraph (V1).

    Champs partagés (entrée/sortie, pattern problem/state.py) :
      user_id / thread_id / query   : entrée run
      workflow_result               : sortie (ResearchResult §8)

    Champs INTERNES (jamais propagés au Main Graph) :
      question / objective / payload / plan / tasks / sources /
      claims / evidence / findings / contradictions /
      missing_information / iteration / max_iterations /
      final_report / errors
    """

    # --- Entrée (partagée) ---
    user_id: str
    thread_id: str
    query: str

    # --- Sortie (partagée) : ResearchResult.model_dump() (§8) ---
    workflow_result: dict

    # --- Interne : formulation ---
    question: str
    objective: str
    payload: dict

    # --- Interne : plan de recherche borné ---
    plan: list          # list[dict] {query, focus, subject, topic, language}
    tasks: list         # file résiduelle (liste de dicts, consommée)

    # --- Interne : collecte ---
    sources: list       # sources web normalisées [{title, source, url,
                        # content, snippet, relevance, source_type}]
    errors: list        # erreurs de recherche (transitoires bornées)

    # --- Interne : extraction / vérification ---
    claims: list        # claims extraits [{claim, source, confidence}]
    evidence: list      # preuves par claim (corroboration, verdict)
    findings: list      # facts notables agrégés (top, sourcés)
    contradictions: list
    missing_information: list

    # --- Interne : pilotage de la boucle bornée ---
    iteration: int
    max_iterations: int

    # --- Interne : rapport final (cf. ResearchResult) ---
    final_report: dict | None


__all__ = ["ResearchState"]