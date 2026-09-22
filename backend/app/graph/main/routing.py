# Main Graph Routing — table de routage des workflows (§26/§28).
#
# Ce module ne contient AUCUNE logique métier : uniquement la
# correspondance workflow → node, consommée par edges.py pour câbler
# les arêtes conditionnelles. Ajouter un workflow = ajouter UNE entrée
# ici + son node dans edges.register_nodes().
#
# Graphe conceptuel :
#
#   START → INTAKE → ROUTER ──(supported/multi_domain)→ RETRIEVAL
#                        │                            │
#                        └─(ambiguous/...)→ FALLBACK  │
#                                              │      │
#                              RETRIEVAL ───────┘      │
#                                │                     │
#                                └──────────→ FALLBACK←┘
#                                                │
#                                                ▼
#                                         WORKFLOW_ROUTER ──(main)→ CONTEXT
#                                                │
#                                                ├─(activity)→ ACTIVITY ─→ CONTEXT
#                                                ├─(problem)→ PROBLEM ─→ CONTEXT
#                                                ├─(research)→ RESEARCH ─→ CONTEXT
#                                                ├─(coding)→ CODING ─→ CONTEXT
#                                                ├─(video)→ VIDEO ─→ CONTEXT
#                                                └─(document)→ DOCUMENT ─→ CONTEXT
#                                                │
#                                                ▼
#                                      CONTEXT → LEARNING → AGENT → RESPONSE → END
#
# Le graphe principal ne contient PAS la logique interne de chaque
# workflow : chaque branche produit son contrat §8 (workflow_result)
# puis rejoint la chaîne principale.
from __future__ import annotations

# Branche WORKFLOW_ROUTER : clé de routage → node destinataire.
# "context" = chaîne principale (workflow "main"), les autres =
# workflows spécialisés qui reviennent TOUS sur "context".
WORKFLOW_BRANCHES: dict[str, str] = {
    "context": "context",
    "activity": "activity",
    "problem": "problem",
    "research": "research",
    "coding": "coding",
    "video": "video",
    "document": "document",
}

# Retour des workflows spécialisés : TOUJOURS la chaîne principale.
SUBGRAPH_RETURN: dict[str, str] = {"context": "context"}

__all__ = ["WORKFLOW_BRANCHES", "SUBGRAPH_RETURN"]
