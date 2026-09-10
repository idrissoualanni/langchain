# Runner — orchestration d'un run agent avec événements observables
import asyncio
import time
from typing import AsyncIterator

from app.agent.graph import get_agent
from app.logging.events import log_event


def _config_for(thread_id: str, user_id: str = "") -> dict:
    """Config LangGraph : thread_id (conversation) + user_id (observabilité)."""
    return {
        "configurable": {
            "thread_id": thread_id,
            "user_id": user_id,
        }
    }


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

    # Messages ajoutés depuis le checkpoint parent
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

    # get_state_history : plus récent d'abord → on inverse pour chrono
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


async def run_agent_stream(
    user_id: str,
    thread_id: str,
    message: str,
) -> AsyncIterator[dict]:
    """Exécute un run complet en streamant les événements du pipeline.

    Pipeline émis (événements réels, jamais simulés) :
      RUN_START → STATE_LOAD → USER_MESSAGE →
      (LLM → TOOL_START → TOOL_END/TOOL_ERROR → LLM …) →
      ASSISTANT_MESSAGE → CHECKPOINT_SAVED → RUN_END
    """
    agent = get_agent()
    config = _config_for(thread_id, user_id)

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

    # ----- State existant -----
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

    # ----- Message utilisateur -----
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

    input_state = {
        "messages": [
            {"role": "user", "content": message}
        ],
        "user_id": user_id,
        "interaction_count": interaction_count,
    }

    # ----- Invoke agent (dans un thread pour ne pas bloquer la loop) -----
    start = time.perf_counter()

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: agent.invoke(input_state, config=config),
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

    # Les événements TOOL_START/TOOL_END/TOOL_ERROR ont été émis
    # en temps réel par ToolEventMiddleware pendant l'invoke —
    # le frontend les reçoit via le bus SSE (filtre thread_id).

    messages = result.get("messages", [])
    last_message = messages[-1] if messages else None
    response_content = ""
    if last_message is not None:
        content = getattr(last_message, "content", "")
        response_content = (
            content if isinstance(content, str) else str(content)
        )

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

    # ----- Checkpoint -----
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

    input_state = {
        "messages": [
            {"role": "user", "content": message}
        ],
        "user_id": user_id,
        "interaction_count": interaction_count,
    }

    result = agent.invoke(input_state, config=config)

    messages = result.get("messages", [])
    last_message = messages[-1] if messages else None
    response_content = ""
    if last_message is not None:
        content = getattr(last_message, "content", "")
        response_content = (
            content if isinstance(content, str) else str(content)
        )

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
