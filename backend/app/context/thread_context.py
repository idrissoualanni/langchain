from app.logging.events import log_event


def build_thread_context(thread_id: str) -> dict:
    """Résumé minimal du thread (métadonnées, pas de contenu).

    L'historique réel des messages est déjà géré par le checkpointer
    et transmis au LLM par LangGraph en tant que messages — ce contexte
    n'ajoute que les métadonnées utiles.

    Retourne {"thread_id": str, "message_count": int|None, "text": str}.
    Émet THREAD_CONTEXT_SELECTED.
    """
    # Le compte de messages est déduit du state au moment de l'appel
    # par le middleware (via get_state) — ici on reste découplé :
    # thread_context n'a pas besoin du state pour construire son bloc.
    text = f"thread_id = {thread_id}" if thread_id else ""

    log_event(
        "THREAD_CONTEXT_SELECTED",
        message=f"Thread context | thread={thread_id}",
        thread_id=thread_id,
        extra={
            "operation": "thread_context",
            "thread_id": thread_id,
            "duplicates_history": False,
        },
    )

    return {
        "thread_id": thread_id,
        "message_count": None,  # rempli par le middleware si dispo
        "text": text,
    }
