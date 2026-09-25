"""
Persistance du transcript vocal.

En fin de session, l'échange parlé est réinjecté dans le thread
LangGraph de l'utilisateur via `aupdate_state` — SANS réexécuter
l'agent. La conversation vocale apparaît alors dans l'historique
clavier au prochain chargement du thread.

On n'écrit pas directement dans SQLite : le checkpointer est la source
de vérité ( get_thread_state lit exactement `values["messages"]` ),
et passer par l'API officielle évite de corrompre le state.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from app.graph.main import get_agent
from app.services.agent.runner import _config_for

logger = logging.getLogger("agent-tutor.livekit")


def _extract_turns(history_messages: list[Any]) -> list[tuple[str, str]]:
    """Extrait les tours ( role, texte ) du ChatContext LiveKit.

    LiveKit utilise ChatMessage avec .role ∈ {system,user,assistant} et
    .content qui peut être str ou liste de parties. On ne garde que les
    tours user/assistant avec du texte exploitable.
    """
    turns: list[tuple[str, str]] = []
    for msg in history_messages:
        role = getattr(msg, "role", None)
        if role not in ("user", "assistant"):
            continue

        content = getattr(msg, "content", None)
        text: str | None = None
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            # Liste de parties ( texte, audio… ) — on concatène le texte
            parts = []
            for part in content:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict):
                    maybe = part.get("text") or part.get("content")
                    if isinstance(maybe, str):
                        parts.append(maybe)
            text = " ".join(p for p in parts if p).strip() or None

        if text:
            turns.append((role, text))
    return turns


async def persist_transcript(
    user_id: str,
    thread_id: str,
    history_messages: list[Any],
) -> int:
    """Réinjecte le transcript vocal dans le thread. Retourne le nombre
    de messages persistés ( 0 si rien à écrire ou thread inexistant ).

    ASYNC : aupdate_state n'a pas de variante synchrone non bloquante ;
    l'unique appelant ( _on_shutdown du worker ) est async — on await
    donc directement, sans asyncio.run.

    Non-fatal : un échec de persistance ne doit JAMAIS casser la
    session vocale — l'utilisateur a déjà eu sa réponse à l'oral.
    """
    try:
        turns = _extract_turns(history_messages)
        if not turns:
            return 0

        agent = get_agent()
        config = _config_for(thread_id, user_id)

        # Snapshot actuel : on n'écrit que si le thread existe déjà.
        # Un thread jamais utilisé n'a pas de checkpoint ; y injecter
        # des messages orphelins créerait un state sans user_id.
        snapshot = agent.get_state(config)
        if not snapshot or not snapshot.values:
            logger.info(
                "thread %s sans checkpoint — transcript non persisté",
                thread_id,
            )
            return 0

        messages: list[Any] = []
        for role, text in turns:
            if role == "user":
                messages.append(HumanMessage(content=text))
            else:
                messages.append(AIMessage(content=text))

        # as_node None : ajoute aux messages sans déclencher un node.
        # aupdate_state ( async ) : la version synchrone update_state
        # fait un checkpoint SQL BLOQUANT — exécuté dans un shutdown
        # callback du worker, elle gèle la boucle asyncio ( et donc
        # l'audio en cours ) pendant l'écriture.
        await agent.aupdate_state(config, {"messages": messages})

        logger.info(
            "transcript vocal persisté | user=%s thread=%s messages=%d",
            user_id,
            thread_id,
            len(messages),
        )
        return len(messages)
    except Exception as exc:  # noqa: BLE001 — voir docstring
        logger.warning("persistance transcript impossible (%s)", exc)
        return 0


def thread_id_from_metadata(metadata: Any) -> str | None:
    """Extrait le thread_id du metadata du dispatch ( JSON ).

    Le backend POST /agent/start passe {"thread_id": ...} dans le
    metadata du dispatch ; le worker le lit via ctx.job.metadata.
    """
    if not metadata:
        return None
    if not isinstance(metadata, str):
        return None
    try:
        payload = json.loads(metadata)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get("thread_id")
    return value if isinstance(value, str) and value.strip() else None
