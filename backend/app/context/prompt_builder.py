# Prompt Builder V5 — PRÉSENTATION uniquement (§35).
#
# Reçoit : BuiltContext (pydantic structuré, déjà sélectionné).
# Produit : le prompt final (str).
#
# Il ne fait AUCUNE requête, AUCUN routing, AUCUNE recherche
# knowledge, AUCUN appel de tool — tout vient du Context Builder.
# Il ne met JAMAIS d'identifiant technique (user_id/thread_id)
# dans le prompt (§36) — seulement des données utiles.
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

    # --- USER CONTEXT (mémoire sélectionnée — données utiles, §36) ---
    if context.user.text:
        parts.append(
            "## USER CONTEXT (mémoire longue durée de l'étudiant)\n\n"
            + context.user.text
        )

    # --- THREAD (léger — PAS l'historique, §32) ---
    if context.thread.text:
        parts.append("## Contexte courant\n\n" + context.thread.text)

    # --- LEARNING (réservé V6+ — toujours absent aujourd'hui) ---
    if context.learning:
        parts.append(
            "## LEARNING CONTEXT\n\n" + str(context.learning)
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
        },
    )
    return prompt
