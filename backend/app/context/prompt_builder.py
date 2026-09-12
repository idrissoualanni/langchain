from app.context.schemas import BuiltContext
from app.logging.events import log_event


def build_system_prompt(
    core_prompt: str,
    context: BuiltContext,
    user_id: str = "",
    thread_id: str = "",
) -> str:
    """Assemble le system prompt final depuis le contexte structuré.

    Structure (§34) : CORE + MATIÈRE + NOTES ROUTING (fallbacks)
    + KNOWLEDGE + USER CONTEXT + THREAD + LEARNING (réservé).
    """
    parts: list[str] = [core_prompt.strip()]

    # --- MATIÈRE (Subject Config — comment enseigner, §12) ---
    subject = context.subject
    if subject:
        lines = [
            f"## MATIÈRE : {subject.name} ({subject.domain})"
        ]
        if subject.description:
            lines.append(subject.description.strip())
        if subject.teaching_style:
            lines.append("")
            lines.append(
                "Style d'enseignement : "
                + ", ".join(subject.teaching_style)
            )
        if subject.pedagogical_guidelines:
            lines.append("")
            lines.append("Guidelines pédagogiques :")
            lines += [
                f"- {g}" for g in subject.pedagogical_guidelines
            ]
        if subject.capabilities:
            lines.append("")
            lines.append(
                "Capacités : " + ", ".join(subject.capabilities)
            )
        parts.append("\n".join(lines))

    # --- NOTES ROUTING (fallbacks = situations normales, §37) ---
    routing = context.routing
    if routing.status == "unsupported":
        parts.append(
            "## NOTE DU SYSTÈME\n\n"
            f"La matière « {routing.subject or 'détectée'} » a été "
            "détectée mais n'a pas encore de configuration "
            "spécialisée. Enseigne en tuteur général et indique "
            "le clairement à l'étudiant."
        )
    elif routing.status == "ambiguous":
        cands = ", ".join(routing.candidates)
        parts.append(
            "## NOTE DU SYSTÈME\n\n"
            f"La question est ambiguë entre : {cands}. Demande une "
            "clarification à l'étudiant au lieu de choisir "
            "arbitrairement."
        )
    elif routing.status == "multi_domain":
        subs = ", ".join(routing.subjects)
        parts.append(
            "## NOTE DU SYSTÈME\n\n"
            f"Question multi-domaines ({subs}). Peux-tu clarifier le "
            "domaine principal visé par l'étudiant ?"
        )

    # --- KNOWLEDGE (quoi enseigner — sections pertinentes) ---
    if context.knowledge.items:
        lines = [
            "## CONNAISSANCES DU COURS (récupérées du knowledge)"
        ]
        for item in context.knowledge.items:
            lines.append("")
            lines.append(f"### {item.source} — {item.topic}")
            lines.append(item.content)
        parts.append("\n".join(lines))
    elif subject and context.knowledge.status in (
        "insufficient",
        "unavailable",
    ):
        # §38 : ne JAMAIS transformer knowledge=none en success
        parts.append(
            "## NOTE DU SYSTÈME\n\n"
            "Aucune connaissance de cours pertinente n'a été trouvée "
            "pour cette question. N'invente pas : enseigne avec tes "
            "connaissances générales, signale que ce contenu ne "
            "provient pas d'une base spécialisée, et propose "
            "recherche_web si pertinent."
        )

    # --- WEB (V6.5 §24/§27) — résultats structurés de la
    #     recherche web de fallback. Source + contenu uniquement,
    #     PAS les métadonnées internes (source_quality...). ---
    if context.web and context.web.results:
        lines = [
            "## RECHERCHE WEB (fallback — le knowledge local "
            "n'avait rien de pertinent)"
        ]
        for r in context.web.results:
            label = r.source or (r.url or "source web")
            lines.append("")
            lines.append(f"### {r.title or label}")
            lines.append(f"Source : {r.url or label}")
            lines.append(r.snippet or r.content[:600])
        lines.append(
            "\nUtilise ces sources web avec précaution : cite-les "
            "naturellement quand tu t'en appuies, n'invente pas "
            "de contenu qu'elles ne contiennent pas."
        )
        parts.append("\n".join(lines))
    elif (
        subject
        and context.knowledge.status == "insufficient"
        and context.web
        and context.web.status in ("insufficient", "unavailable", "error")
    ):
        # §25 : web échoué/insuffisant → General Tutor TRANSPARENT
        parts.append(
            "## NOTE DU SYSTÈME\n\n"
            "Recherche web indisponible ou sans résultat pertinent "
            "(statut : "
            + context.web.status
            + "). Enseigne en tuteur général : réponds avec tes "
            "propres connaissances et signale honnêtement que ce "
            "contenu ne provient d'aucune base vérifiée."
        )

    # --- USER CONTEXT (mémoire sélectionnée — données utiles, §36) ---
    if context.user.text:
        parts.append(
            "## USER CONTEXT (mémoire longue durée de l'étudiant)\n\n"
            + context.user.text
        )

    # --- THREAD (léger — PAS l'historique, §32) ---
    if context.thread.text:
        parts.append("## Contexte courant\n\n" + context.thread.text)

    # --- LEARNING (V6 §24/§25 — progression du topic courant) ---
    # Format voulu par le brief : Mastery / Weak point / Attempts,
    # uniquement pour le subject/topic de la question — jamais
    # toute la progression (pas de biologie pour du Python).
    learning = context.learning
    if isinstance(learning, dict) and learning.get("status") == "active":
        lines = [
            "## LEARNING (progression de l'étudiant sur ce topic)"
        ]
        topic_label = (
            f"{learning.get('subject') or '?'} / "
            f"{learning.get('topic') or '?'}"
        )
        lines.append(f"Topic : {topic_label}")

        mastery = learning.get("mastery")
        if mastery is not None:
            pct = round(mastery * 100)
            lines.append(f"Mastery : {pct}%")
            conf = learning.get("confidence")
            if conf is not None:
                lines.append(
                    f"(estimation — confiance {round(conf * 100)}%)"
                )
        else:
            lines.append(
                "Mastery : pas encore évalué (topic jamais travaillé)"
            )

        attempts = learning.get("attempts") or 0
        lines.append(f"Attempts : {attempts}")

        strengths = learning.get("strengths") or []
        if strengths:
            lines.append(
                "Strengths : " + " ; ".join(strengths[:3])
            )
        weak_points = learning.get("weak_points") or []
        if weak_points:
            lines.append(
                "Weak points : " + " ; ".join(weak_points[:3])
            )

        if learning.get("last_assessed_at"):
            lines.append(
                f"Dernière évaluation : "
                f"{learning['last_assessed_at'][:10]}"
            )

        goal = learning.get("goal")
        if goal and goal.get("status") == "active":
            lines.append(
                f"Objectif actif : {goal.get('description', '')}"
            )

        lines.append(
            "Adapte ton enseignement à cette progression : "
            "consolide les weak points, appuie-toi sur les strengths."
        )
        parts.append("\n".join(lines))

    elif (
        isinstance(learning, dict)
        and learning.get("status") == "not_started"
        and routing.status == "supported"
        and subject
    ):
        # §26 : absence de progression = premier contact, pas
        # une erreur — le tuteur adapte (évaluer avant d'approfondir).
        parts.append(
            "## LEARNING\n\nPas encore de progression suivie sur "
            "cette matière — premier contact probable. Commence "
            "par évaluer le niveau avec un exercice simple avant "
            "d'approfondir."
        )

    prompt = "\n\n".join(p for p in parts if p.strip())

    log_event(
        "PROMPT_BUILD",
        message=(
            f"Prompt built | user={user_id} | "
            f"total_chars={len(prompt)} | "
            f"subject={routing.subject} | "
            f"knowledge={len(context.knowledge.items)}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        extra={
            "operation": "prompt_build",
            "total_chars": len(prompt),
            "subject": routing.subject,
            "knowledge_items": len(context.knowledge.items),
            "memories_used": len(context.relevant_memories),
            "learning_status": (
                context.learning.get("status")
                if isinstance(context.learning, dict)
                else None
            ),
        },
    )
    return prompt
