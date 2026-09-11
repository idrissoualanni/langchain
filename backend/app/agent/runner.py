# Runner V5 — orchestration d'un run agent (§61).
#
# Changement V5 : user_id/thread_id transportés via le RUNTIME
# CONTEXT natif (context=AgentContext(...), §4) en PLUS du
# configurable (thread_id requis par le checkpointer ; user_id
# conservé dans configurable pour rétrocompatibilité observabilité
# — la source de vérité du middleware est désormais le runtime).
import asyncio
import time
from typing import AsyncIterator

from app.agent.graph import get_agent
from app.context.schemas import AgentContext
from app.logging.events import log_event


def _config_for(thread_id: str, user_id: str = "") -> dict:
    """Config LangGraph : thread_id (conversation, checkpointer §7)
    + user_id (observabilité logs)."""
    return {
        "configurable": {
            "thread_id": thread_id,
            "user_id": user_id,
        }
    }


def _runtime_context(user_id: str, thread_id: str) -> AgentContext:
    """Runtime Context natif LangGraph (§4) — DI pour middleware
    et tools (request.runtime.context.user_id)."""
    return AgentContext(user_id=user_id, thread_id=thread_id)


def _message_to_dict(message) -> dict:
    """Convertit un message LangChain en dict simple pour l'API."""
    msg_type = type(message).__name__

    content = getattr(message, "content", "")
    if not isinstance(content, str):
        try:
            import json

            content = json.dumps(content, ensure_ascii=False, default=str)
        except Exception:
            content = str(content)

    tool_calls = None
    raw_calls = getattr(message, "tool_calls", None)
    if raw_calls:
        tool_calls = [
            {
                "name": call.get("name", ""),
                "args": call.get("args", {}),
            }
            for call in raw_calls
        ]

    return {
        "type": msg_type,
        "content": content,
        "tool_calls": tool_calls,
    }


def get_thread_state(user_id: str, thread_id: str) -> dict | None:
    """State courant d'un thread depuis le checkpointer (None si vide)."""
    agent = get_agent()
    snapshot = agent.get_state(_config_for(thread_id, user_id))
    if not snapshot or not snapshot.values:
        return None

    values = snapshot.values
    messages = [
        _message_to_dict(m) for m in values.get("messages", [])
    ]

    return {
        "user_id": values.get("user_id", ""),
        "thread_id": thread_id,
        "interaction_count": values.get("interaction_count", 0),
        "message_count": len(messages),
        "messages": messages,
    }


def _checkpoint_summary(snapshot, parent_messages_count: int) -> str:
    """Résumé lisible d'un checkpoint : nature du dernier message ajouté."""
    values = snapshot.values or {}
    messages = values.get("messages", [])
    if len(messages) <= parent_messages_count:
        return "State checkpoint"

    added = messages[parent_messages_count:]
    last = added[-1]

    msg_type = type(last).__name__
    if msg_type == "HumanMessage":
        content = getattr(last, "content", "")
        if isinstance(content, str) and content:
            return f'User message "{content[:60]}..."' if len(content) > 60 else f'User message "{content}"'
        return "User message"
    if msg_type == "AIMessage":
        tool_calls = getattr(last, "tool_calls", None)
        if tool_calls:
            names = ", ".join(
                c.get("name", "?") for c in tool_calls
            )
            return f"Tool call: {names}"
        return "Assistant response"
    if msg_type == "ToolMessage":
        name = getattr(last, "name", "tool")
        return f"Tool result ({name})"

    return f"Message ({msg_type})"


def get_thread_history(user_id: str, thread_id: str) -> list[dict]:
    """Historique des checkpoints d'un thread (chronologique)."""
    agent = get_agent()

    snapshots = []
    for snapshot in agent.get_state_history(_config_for(thread_id, user_id)):
        snapshots.append(snapshot)

    snapshots.reverse()

    history = []
    parent_count = 0
    for snapshot in snapshots:
        values = snapshot.values or {}
        messages = values.get("messages", [])
        checkpoint_id = (
            snapshot.config.get("configurable", {}).get("checkpoint_id")
        )

        history.append(
            {
                "checkpoint_id": checkpoint_id,
                "created_at": (
                    str(snapshot.created_at)
                    if getattr(snapshot, "created_at", None)
                    else ""
                ),
                "message_count": len(messages),
                "interaction_count": values.get(
                    "interaction_count", 0
                ),
                "summary": _checkpoint_summary(
                    snapshot, parent_count
                ),
            }
        )
        parent_count = len(messages)

    return history


def _extract_response(result: dict) -> str:
    """Contenu du dernier message assistant du résultat."""
    messages = result.get("messages", [])
    last_message = messages[-1] if messages else None
    if last_message is not None:
        content = getattr(last_message, "content", "")
        return content if isinstance(content, str) else str(content)
    return ""


def _build_input(user_id: str, message: str, interaction_count: int) -> dict:
    """Input state du run (§62 : user_id dans le state persisté,
    interaction_count compteur du thread)."""
    return {
        "messages": [{"role": "user", "content": message}],
        "user_id": user_id,
        "interaction_count": interaction_count,
    }


async def run_agent_stream(
    user_id: str,
    thread_id: str,
    message: str,
) -> AsyncIterator[dict]:
    """Exécute un run complet en streamant les événements du pipeline.

    Pipeline émis (événements réels, jamais simulés) :
      RUN_START → STATE_LOAD → USER_MESSAGE →
      (ROUTING → CONTEXT_BUILD → PROMPT_BUILD → LLM → TOOLS …) →
      ASSISTANT_MESSAGE → CHECKPOINT_SAVED → RUN_END
    """
    agent = get_agent()
    config = _config_for(thread_id, user_id)
    context = _runtime_context(user_id, thread_id)

    log_event(
        "RUN_START",
        message=f"Run started",
        user_id=user_id,
        thread_id=thread_id,
    )
    yield {
        "event": "RUN_START",
        "level": "INFO",
        "user_id": user_id,
        "thread_id": thread_id,
        "message": "Run started",
    }

    # ----- State existant (checkpointer, §7) -----
    previous = agent.get_state(config)
    previous_values = previous.values if previous else {}
    interaction_count = (
        previous_values.get("interaction_count", 0) + 1
    )
    previous_message_count = len(
        previous_values.get("messages", [])
    )

    log_event(
        "STATE_LOAD",
        message=f"State loaded | messages={previous_message_count} | interaction={interaction_count}",
        user_id=user_id,
        thread_id=thread_id,
    )
    yield {
        "event": "STATE_LOAD",
        "level": "INFO",
        "user_id": user_id,
        "thread_id": thread_id,
        "message": f"State loaded ({previous_message_count} messages)",
        "interaction_count": interaction_count,
    }

    log_event(
        "USER_MESSAGE",
        message=message,
        user_id=user_id,
        thread_id=thread_id,
    )
    yield {
        "event": "USER_MESSAGE",
        "level": "INFO",
        "user_id": user_id,
        "thread_id": thread_id,
        "message": message,
    }

    input_state = _build_input(user_id, message, interaction_count)

    start = time.perf_counter()

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: agent.invoke(
                input_state, config=config, context=context
            ),
        )
    except Exception as exc:
        log_event(
            "ERROR",
            level="ERROR",
            message=f"Agent error: {exc}",
            user_id=user_id,
            thread_id=thread_id,
        )
        yield {
            "event": "ERROR",
            "level": "ERROR",
            "user_id": user_id,
            "thread_id": thread_id,
            "message": f"Agent error: {exc}",
        }
        return

    duration_ms = int((time.perf_counter() - start) * 1000)

    response_content = _extract_response(result)

    log_event(
        "ASSISTANT_MESSAGE",
        message=response_content[:500],
        user_id=user_id,
        thread_id=thread_id,
    )
    yield {
        "event": "ASSISTANT_MESSAGE",
        "level": "INFO",
        "user_id": user_id,
        "thread_id": thread_id,
        "message": response_content,
        "response": response_content,
    }

    new_state = agent.get_state(config)
    new_count = len(new_state.values.get("messages", []))
    checkpoint_id = (
        new_state.config.get("configurable", {}).get(
            "checkpoint_id"
        )
        if new_state
        else None
    )

    log_event(
        "CHECKPOINT_SAVED",
        message=f"Checkpoint saved | messages={new_count}",
        user_id=user_id,
        thread_id=thread_id,
        extra={"checkpoint_id": checkpoint_id},
    )
    yield {
        "event": "CHECKPOINT_SAVED",
        "level": "INFO",
        "user_id": user_id,
        "thread_id": thread_id,
        "message": f"Checkpoint saved ({new_count} messages)",
        "checkpoint_id": checkpoint_id,
    }

    log_event(
        "RUN_END",
        message=f"Run completed in {duration_ms}ms",
        user_id=user_id,
        thread_id=thread_id,
    )
    yield {
        "event": "RUN_END",
        "level": "INFO",
        "user_id": user_id,
        "thread_id": thread_id,
        "message": f"Run completed in {duration_ms}ms",
        "duration_ms": duration_ms,
        "interaction_count": interaction_count,
    }


def run_agent(user_id: str, thread_id: str, message: str) -> dict:
    """Mode synchrone (POST /api/chat) — même pipeline, sans stream."""
    agent = get_agent()
    config = _config_for(thread_id, user_id)
    context = _runtime_context(user_id, thread_id)

    log_event(
        "RUN_START",
        message="Run started",
        user_id=user_id,
        thread_id=thread_id,
    )

    previous = agent.get_state(config)
    previous_values = previous.values if previous else {}
    interaction_count = (
        previous_values.get("interaction_count", 0) + 1
    )

    log_event(
        "STATE_LOAD",
        message=f"State loaded | interaction={interaction_count}",
        user_id=user_id,
        thread_id=thread_id,
    )

    log_event(
        "USER_MESSAGE",
        message=message,
        user_id=user_id,
        thread_id=thread_id,
    )

    input_state = _build_input(user_id, message, interaction_count)

    result = agent.invoke(
        input_state, config=config, context=context
    )

    response_content = _extract_response(result)

    log_event(
        "ASSISTANT_MESSAGE",
        message=response_content[:500],
        user_id=user_id,
        thread_id=thread_id,
    )

    new_state = agent.get_state(config)
    log_event(
        "CHECKPOINT_SAVED",
        message="Checkpoint saved",
        user_id=user_id,
        thread_id=thread_id,
    )
    log_event(
        "RUN_END",
        message="Run completed",
        user_id=user_id,
        thread_id=thread_id,
    )

    return {
        "response": response_content,
        "user_id": user_id,
        "thread_id": thread_id,
        "interaction_count": interaction_count,
    }
