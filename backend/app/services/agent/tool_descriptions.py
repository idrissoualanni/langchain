# Descriptions explicites des tools du LLM — source unique.
#
# Ce module centralise, pour CHAQUE tool de `all_tools`, une notice
# pédagogique courte : QUAND l'utiliser, COMMENT, et QUELLE CARTE
# frontend elle déclenche (contrat schemas/response.AgentResponse.type).
#
# Il est RELIÉ :
#   - au prompt système : build_tool_catalog() injecte le catalogue
#     dans CORE_PROMPT (section "Catalogue des tools") ;
#   - aux schémas de sortie : chaque entrée référence le type public
#     attendu (`response_type`) pour que tool → normalizer → carte
#     restent alignés. Un test (tests/test_tool_descriptions.py)
#     vérifie que les 27 tools sont couverts et que les types cités
#     existent dans le contrat.

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolDescription:
    """Notice d'un tool pour le prompt système."""

    name: str          # nom EXACT du tool (@tool name=…)
    family: str        # famille (search/memory/pedagogical/learning/code/documents)
    when: str          # quand l'appeler (une phrase imperative)
    how: str           # paramètres clés / précautions d'appel
    response_type: str # type public AgentResponse produit ou "text"


TOOL_DESCRIPTIONS: tuple[ToolDescription, ...] = (
    # ── Recherche ────────────────────────────────────────────────
    ToolDescription(
        name="recherche_web",
        family="search",
        when="Question hors base de cours, actualité, ou complément quand aucune connaissance de cours n'a été trouvée.",
        how="query court et précis ; cite les sources retournées dans ta réponse, ne les invente jamais.",
        response_type="search",
    ),
    # ── Mémoire (profil + faits) ─────────────────────────────────
    ToolDescription(
        name="get_user_profile",
        family="memory",
        when="Besoin du profil global (niveau, objectifs) non présent dans le USER CONTEXT du prompt.",
        how="user_id persistant (jamais thread_id).",
        response_type="text",
    ),
    ToolDescription(
        name="update_user_profile",
        family="memory",
        when="L'étudiant déclare explicitement un changement de niveau, d'objectif ou de contexte durable.",
        how="Un seul champ par appel ; jamais d'hypothèse déduite du comportement.",
        response_type="text",
    ),
    ToolDescription(
        name="get_user_memory",
        family="memory",
        when="Le USER CONTEXT fourni est insuffisant pour répondre.",
        how="category=None pour lister tout ; sinon identity/background/personality/preference/interest.",
        response_type="text",
    ),
    ToolDescription(
        name="save_user_memory",
        family="memory",
        when="UN fait durable explicitement déclaré par l'étudiant (nom, formation, préférence, intérêt).",
        how="Un fait par appel, jamais de fusion ; en cas de doute, ne pas enregistrer.",
        response_type="text",
    ),
    ToolDescription(
        name="update_user_memory",
        family="memory",
        when="Un fait existant devient faux ou doit être corrigé.",
        how="Nécessite l'id exact du fait (obtenu via get/search_user_memory).",
        response_type="text",
    ),
    ToolDescription(
        name="delete_user_memory",
        family="memory",
        when="L'étudiant demande explicitement d'oublier un fait.",
        how="Un seul id par suppression.",
        response_type="text",
    ),
    ToolDescription(
        name="search_user_memory",
        family="memory",
        when="Retrouver un fait précis parmi la mémoire longue.",
        how="Requête sémantique courte.",
        response_type="text",
    ),
    # ── Pédagogie (activités structurées) ────────────────────────
    ToolDescription(
        name="create_exercise",
        family="pedagogical",
        when="Demande d'exercice sur un topic d'une matière supportée — IMMÉDIATEMENT, sans demander de sous-aspect d'abord.",
        how="subject + topic ; le contenu vient de la base de cours. Ouvre une activité interactive : pose la question puis STOP, attends la réponse.",
        response_type="exercise",
    ),
    ToolDescription(
        name="evaluate_answer",
        family="pedagogical",
        when="L'étudiant a répondu à une activité ouverte. TOUJOURS évaluer via le tool avant tout commentaire.",
        how="Compare au contenu réel du cours : score 0..1 + termes manquants. Puis OBLIGATOIREMENT record_learning_observation avec ces valeurs.",
        response_type="evaluation",
    ),
    ToolDescription(
        name="give_hint",
        family="pedagogical",
        when="Demande d'indice ou blocage (« je suis bloqué ») — AVANT de formuler ton propre indice.",
        how="level croissant 0→1→2 (orientation → précision → presque solution). Jamais level 2 d'emblée.",
        response_type="hint",
    ),
    ToolDescription(
        name="create_quiz",
        family="pedagogical",
        when="Quiz demandé — livre UNE seule question.",
        how="Ne jamais dévoiler les N questions d'un coup ; la suivante passe par create_quiz_next après évaluation.",
        response_type="quiz",
    ),
    ToolDescription(
        name="create_quiz_next",
        family="pedagogical",
        when="Question suivante du quiz EN COURS, uniquement après évaluation + feedback de la précédente.",
        how="Reprend l'activité quiz ouverte du thread.",
        response_type="quiz",
    ),
    ToolDescription(
        name="assess_understanding",
        family="pedagogical",
        when="Après une réponse CORRECTE, avant de conclure — distingue réussite et compréhension réelle.",
        how="Passe la réponse de l'étudiant ; suis son retour (conclude / ask_followup / give_hint / re_explain).",
        response_type="clarification",
    ),
    ToolDescription(
        name="propose_review",
        family="pedagogical",
        when="Point faible récurrent détecté (via get_learning_topic) justifiant une révision espacée.",
        how="Proposition à l'étudiant, jamais imposée.",
        response_type="text",
    ),
    ToolDescription(
        name="create_diagram",
        family="pedagogical",
        when="Une structure/processus gagne à être DESSINÉ (flux algo, classes, machine à états, BDD, chronologie). Voie privilégiée sur le bloc markdown.",
        how="chart = code mermaid BRUT SANS fence, mot-clé en 1ʳᵉ ligne, ≤15 nœuds ; caption courte. Activité NON interactive : n'attends pas de réponse, n'évalue pas dessus, et n'écris PAS de bloc ```mermaid dans le même tour.",
        response_type="diagram",
    ),
    # ── Apprentissage (progression) ──────────────────────────────
    ToolDescription(
        name="get_learning_profile",
        family="learning",
        when="Vue d'ensemble de la progression toutes matières, pour adapter le rythme.",
        how="user_id persistant.",
        response_type="text",
    ),
    ToolDescription(
        name="get_learning_topic",
        family="learning",
        when="AVANT d'enseigner un topic déjà travaillé — pour t'adapter au mastery réel.",
        how="subject + topic ; renvoie scores faibles et historique.",
        response_type="text",
    ),
    ToolDescription(
        name="record_learning_observation",
        family="learning",
        when="OBLIGATOIRE après chaque evaluate_answer (même tour ou suivant). Sans cela la progression est PERDUE.",
        how="subject/topic exacts, observation_type='exercise', score et weak_points/strengths REPRIS du tool (jamais inventés).",
        response_type="text",
    ),
    ToolDescription(
        name="update_learning_goal",
        family="learning",
        when="L'étudiant fixe ou modifie explicitement un objectif d'apprentissage.",
        how="Objectif mesurable, formulé avec lui.",
        response_type="text",
    ),
    # ── Code (si la matière l'autorise) ──────────────────────────
    ToolDescription(
        name="execute_code",
        family="code",
        when="Faire tourner le code de l'étudiant pour objectiver un comportement. Nécessite une matière qui l'autorise.",
        how="NE RÉÉCRIS JAMAIS son code sans permission : identifie → explique → questionne → indice.",
        response_type="code",
    ),
    ToolDescription(
        name="run_tests",
        family="code",
        when="Valider le code de l'étudiant contre des tests du cours.",
        how="Commente les échecs un par un, laisse-le corriger et relancer.",
        response_type="code",
    ),
    ToolDescription(
        name="analyze_code",
        family="code",
        when="Retour statique (lisibilité, pièges) sur le snippet de l'étudiant.",
        how="Orientant, jamais réécriture automatique.",
        response_type="code",
    ),
    # ── Documents (base personnelle de l'étudiant) ───────────────
    ToolDescription(
        name="upload_document",
        family="documents",
        when="L'étudiant fournit un document personnel à intégrer à sa base.",
        how="Confirmer le titre/indexation retourné.",
        response_type="text",
    ),
    ToolDescription(
        name="search_documents",
        family="documents",
        when="Question portant sur les documents PERSONNELS de l'étudiant.",
        how="Citer le document source ; distinguer clairement cours officiel vs document perso.",
        response_type="search",
    ),
    ToolDescription(
        name="list_documents",
        family="documents",
        when="Inventaire de la base documentaire de l'étudiant.",
        how="Liste simple, sans détailler le contenu.",
        response_type="text",
    ),
    ToolDescription(
        name="delete_document",
        family="documents",
        when="Demande explicite de suppression d'un document.",
        how="document_id exact obtenu via list_documents.",
        response_type="text",
    ),
)


def build_tool_catalog() -> str:
    """Rend le catalogue Markdown injecté dans le prompt système.

    Regroupé par famille, une ligne par tool :
    `- nom — quand. Comment.` La carte frontend produite est rappelée
    entre crochets pour les réponses structurées.
    """
    families: dict[str, list[ToolDescription]] = {}
    for td in TOOL_DESCRIPTIONS:
        families.setdefault(td.family, []).append(td)

    lines: list[str] = []
    for family, items in families.items():
        lines.append(f"### {family}")
        for td in items:
            card = f" [carte: {td.response_type}]" if td.response_type != "text" else ""
            lines.append(f"- **{td.name}** — {td.when} {td.how}{card}")
    return "\n".join(lines)


__all__ = ["ToolDescription", "TOOL_DESCRIPTIONS", "build_tool_catalog"]
