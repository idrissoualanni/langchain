# Prompt Builder V4 — assemble le system prompt dynamique.
# Structure (§24) : CORE + MATIÈRE + TOPIC + USER + THREAD + KNOWLEDGE
#                  + TOOLS + LEARNING (réservé).
# Context Builder sélectionne ; Prompt Builder présente au modèle.
from app.logging.events import log_event


def build_system_prompt(
    core_prompt: str,
    context: dict,
    user_id: str = "",
    thread_id: str = "",
) -> str:
    """Assemble le system prompt final depuis le contexte structuré."""
    parts: list[str] = [core_prompt.strip()]

    # --- MATIÈRE (Subject Config) ---
    subject = context.get("subject")
    if subject:
        lines = [
            f"## MATIÈRE : {subject['name']} ({subject['domain']})"
        ]
        if subject.get("description"):
            lines.append(subject["description"].strip())
        if subject.get("teaching_style"):
            lines.append("")
            lines.append(
                "Style d'enseignement : "
                + ", ".join(subject["teaching_style"])
            )
        if subject.get("pedagogical_guidelines"):
            lines.append("")
            lines.append("Guidelines pédagogiques :")
            lines += [f"- {g}" for g in subject["pedagogical_guidelines"]]
        if subject.get("capabilities"):
            lines.append("")
            lines.append(
                "Capacités : " + ", ".join(subject["capabilities"])
            )
        parts.append("\n".join(lines))

    # --- ROUTER NOTES (status non-supported → instructions) ---
    router = context.get("router") or {}
    status = router.get("status")
    if status == "unsupported":
        note = (
            "## NOTE DU SYSTÈME\n\n"
            f"La matière « {router.get('subject') or 'détectée'} » a été "
            "détectée mais n'a pas encore de configuration spécialisée. "
            "Enseigne en tuteur général et indique le clairement à "
            "l'étudiant."
        )
        parts.append(note)
    elif status == "ambiguous":
        cands = ", ".join(router.get("candidates") or [])
        note = (
            "## NOTE DU SYSTÈME\n\n"
            f"La question est ambiguë entre : {cands}. Demande une "
            "clarification à l'étudiant au lieu de choisir arbitrairement."
        )
        parts.append(note)
    elif status == "multi_domain":
        subs = ", ".join(router.get("subjects") or [])
        note = (
            "## NOTE DU SYSTÈME\n\n"
            f"Question multi-domaines ({subs}). Peux-tu clarifier le "
            "domaine principal visé par l'étudiant ?"
        )
        parts.append(note)

    # --- KNOWLEDGE ---
    knowledge = context.get("knowledge") or {}
    if knowledge.get("items"):
        lines = [
            "## CONNAISSANCES DU COURS (récupérées du knowledge)"
        ]
        for item in knowledge["items"]:
            lines.append("")
            lines.append(
                f"### {item['source']} — {item['topic']}"
            )
            lines.append(item["content"])
        parts.append("\n".join(lines))
    elif subject and knowledge.get("status") in (
        "insufficient",
        "unavailable",
    ):
        note = (
            "## NOTE DU SYSTÈME\n\n"
            "Aucune connaissance de cours pertinente n'a été trouvée pour "
            "cette question. N'invente pas : enseigne avec tes "
            "connaissances générales, signale que ce contenu ne provient "
            "pas d'une base spécialisée, et propose recherche_web si "
            "pertinent."
        )
        parts.append(note)

    # --- USER CONTEXT ---
    user_text = (context.get("user") or {}).get("text", "")
    if user_text:
        parts.append(
            "## USER CONTEXT (mémoire longue durée de l'étudiant)\n\n"
            + user_text
        )

    # --- THREAD ---
    thread_text = (context.get("thread") or {}).get("text", "")
    if thread_text:
        parts.append("## Contexte courant\n\n" + thread_text)

    # --- LEARNING (réservé V5+) ---
    learning = context.get("learning")
    if learning:
        parts.append("## LEARNING CONTEXT\n\n" + str(learning))

    prompt = "\n\n".join(p for p in parts if p.strip())

    log_event(
        "PROMPT_BUILD",
        message=(
            f"Prompt built | user={user_id} | "
            f"total_chars={len(prompt)} | "
            f"subject={router.get('subject')} | "
            f"knowledge={len(knowledge.get('items', []))}"
        ),
        user_id=user_id,
        thread_id=thread_id,
        extra={
            "operation": "prompt_build",
            "total_chars": len(prompt),
            "subject": router.get("subject"),
            "knowledge_items": len(knowledge.get("items", [])),
            "memories_used": len(
                context.get("relevant_memories") or []
            ),
        },
    )
    return prompt
