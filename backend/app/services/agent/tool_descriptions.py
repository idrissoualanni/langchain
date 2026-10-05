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
#     vérifie que tous les tools sont couverts et que les types cités
#     existent dans le contrat.
#
# Porté du commit qwen.ai[bot] 864f094 et ADAPTÉ à l'inventaire réel
# de master (34 tools + create_diagram) : les entrées référençant
# l'ancienne API mémoire (get_user_memory, save_user_memory,
# update_user_memory) et l'ancien update_learning_goal ont été
# retirées ; la famille mémoire/apprentissage actuelle est couverte.

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
        when="Question hors base de cours, actualité, ou complément quand aucune connaissance de cours n'a été trouvée. INTERDIT lors de la génération d'exercices ou de l'évaluation d'une réponse.",
        how="query court et précis ; cite les sources retournées dans ta réponse, ne les invente jamais.",
        response_type="search",
    ),
    # ── Connaissance de cours (corpus validé) ────────────────────
    ToolDescription(
        name="search_knowledge",
        family="knowledge",
        when="Besoin d'un extrait PRÉCIS du cours d'une matière (définition, détail) au-delà du contexte déjà injecté.",
        how="subject = identifiant de matière (ex: python) ; query ciblé ; cite les extraits et leur auteur, ne les invente jamais.",
        response_type="search",
    ),
    ToolDescription(
        name="propose_knowledge",
        family="knowledge",
        when="L'agent identifie un complément de cours fiable et manquant (définition, exemple, précision) qu'il veut soumettre.",
        how="subject = matière existante ; title court ; content Markdown ; reason. La proposition n'entre au corpus qu'APRÈS validation admin.",
        response_type="text",
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
        name="get_learner_facts",
        family="memory",
        when="Lister les faits durables mémorisés sur l'apprenant (mémoire longue durée).",
        how="Lecture seule ; category=None pour tout lister.",
        response_type="text",
    ),
    ToolDescription(
        name="save_learner_fact",
        family="memory",
        when="UN fait durable explicitement déclaré par l'étudiant (nom, formation, préférence, intérêt).",
        how="Un fait par appel, jamais de fusion ; en cas de doute, ne pas enregistrer.",
        response_type="text",
    ),
    ToolDescription(
        name="update_learner_fact",
        family="memory",
        when="Un fait existant devient faux ou doit être corrigé.",
        how="Nécessite l'id exact du fait (obtenu via get_learner_facts / search_user_memory).",
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
    ToolDescription(
        name="search_memories",
        family="memory",
        when="Recherche transversale dans TOUTE la mémoire pédagogique (profil, faits, objectifs, sessions) avant de répondre sur l'historique de l'apprenant.",
        how="Requête courte ; exploite les résultats sans les inventer.",
        response_type="text",
    ),
    ToolDescription(
        name="forget_memory",
        family="memory",
        when="Demande RGPD de suppression des données de l'apprenant (« oublie tout sur moi »).",
        how="Action IRRÉVERSIBLE : confirme l'intention de l'étudiant avant l'appel.",
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
        name="create_illustration",
        family="pedagogical",
        when="Une structure, un processus ou une comparaison gagne à être ILLUSTRÉ (flux algo, classes, BDD, chronologie via 'diagram' ; synthèses, comparaisons via 'table'). Voie privilégiée sur le bloc markdown.",
        how="illustration_type = 'diagram' ou 'table' ; content = code mermaid brut (sans fence, ≤15 nœuds) pour diagram, ou données structurées pour table ; caption courte. Activité NON interactive.",
        response_type="illustration",
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
        name="create_learning_goal",
        family="learning",
        when="L'étudiant fixe un NOUVEL objectif d'apprentissage, formulé avec lui et mesurable.",
        how="subject/topic + échéance réaliste ; confirme la formulation à l'étudiant.",
        response_type="text",
    ),
    ToolDescription(
        name="complete_learning_goal",
        family="learning",
        when="L'étudiant atteste avoir atteint un objectif — marque-le terminé.",
        how="goal_id exact (via get_learning_profile) ; célèbre brièvement la réussite.",
        response_type="text",
    ),
    ToolDescription(
        name="update_goal_progress",
        family="learning",
        when="La progression d'un objectif existant change (étape franchie, report, abandon).",
        how="goal_id + statut cible ; ne devine jamais un changement non exprimé.",
        response_type="text",
    ),
    ToolDescription(
        name="get_strong_concepts",
        family="learning",
        when="Bilan de ce qui est maîtrisé (mastery élevé) — pour consolider ou sauter des rappels.",
        how="subject optionnelle pour filtrer.",
        response_type="text",
    ),
    ToolDescription(
        name="get_weak_concepts",
        family="learning",
        when="Cibler les révisions (mastery faible) — avant de proposer un exercice ou une révision espacée.",
        how="subject optionnelle pour filtrer ; propose propose_review si le point faible revient.",
        response_type="text",
    ),
    ToolDescription(
        name="get_past_session_summaries",
        family="learning",
        when="Reprendre le fil d'une session précédente (« la dernière fois on faisait quoi ? »).",
        how="Lecture seule ; ancre tes rappels sur ces résumés réels.",
        response_type="text",
    ),
    ToolDescription(
        name="save_session_summary",
        family="learning",
        when="FIN de session — consigne un résumé structuré de ce qui a été travaillé.",
        how="Faits pédagogiques uniquement (topics, scores, prochaines étapes), pas de conversation brute.",
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
