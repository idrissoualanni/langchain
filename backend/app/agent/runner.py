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
from app.config import (
    AGENT_RECURSION_LIMIT,
    AGENT_TIMEOUT_SECONDS,
    MODEL_RETRY_ATTEMPTS,
)
from app.schemas.context import AgentContext
from app.logging.events import log_event
from app.models.retry import (
    invoke_llm_with_retry,
    invoke_llm_with_retry_sync,
)


def _config_for(thread_id: str, user_id: str = "") -> dict:
    """Config LangGraph : thread_id (conversation, checkpointer §7)
    + user_id (observabilité logs) + recursion_limit (borne de la
    boucle agentique, mission §3 — jamais la valeur LangGraph 10007)."""
    return {
        # Borne réelle de la boucle agentique (mission §3) : la voie
        # LangGraph officielle (config d'invocation, pas compile).
        "recursion_limit": AGENT_RECURSION_LIMIT,
        "configurable": {
            "thread_id": thread_id,
            "user_id": user_id,
        },
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


def _checkpoint_summary(
    snapshot, parent_messages_count: int
) -> tuple[str, str]:
    """Résumé d'un checkpoint : (kind structuré, texte lisible).

    V6.8 (audit §62 G.3) : le frontend consomme `kind` —
    plus JAMAIS de parsing du texte summary (anti-pattern
    §18). kind ∈ user_message / tool_call / tool_result /
    assistant / state / message.
    """
    values = snapshot.values or {}
    messages = values.get("messages", [])
    if len(messages) <= parent_messages_count:
        return "state", "State checkpoint"

    added = messages[parent_messages_count:]
    last = added[-1]

    msg_type = type(last).__name__
    if msg_type == "HumanMessage":
        content = getattr(last, "content", "")
        if isinstance(content, str) and content:
            s = (
                f'User message "{content[:60]}..."' 
                if len(content) > 60
                else f'User message "{content}"'
            )
        else:
            s = "User message"
        return "user_message", s
    if msg_type == "AIMessage":
        tool_calls = getattr(last, "tool_calls", None)
        if tool_calls:
            names = ", ".join(
                c.get("name", "?") for c in tool_calls
            )
            return "tool_call", f"Tool call: {names}"
        return "assistant", "Assistant response"
    if msg_type == "ToolMessage":
        name = getattr(last, "name", "tool")
        return (
            "tool_result",
            f"Tool result ({name})",
        )

    return "message", f"Message ({msg_type})"


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
        kind, summary = _checkpoint_summary(snapshot, parent_count)

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
                "kind": kind,
                "summary": summary,
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


def _build_input(
    user_id: str,
    message: str,
    interaction_count: int,
    workflow: str | None = None,
    payload: dict | None = None,
) -> dict:
    """Input state du run (§62 : user_id dans le state persisté,
    interaction_count compteur du thread).

    workflow : hint émis par le composer (@mention → terme). Canal
    dédié workflow_hint consommé par WORKFLOW_ROUTER. Chaîne vide si
    aucun hint (comportement historique préservé).
    payload : entrée structurée du workflow (§8 SubgraphInput) —
    research_mode, source vidéo… Canal dédié payload consommé par les
    nodes subgraph. Sanitised ici : clés str non vides, valeurs
    scalaires uniquement (jamais de nested, jamais de code exécutable).
    """
    clean: dict = {}
    if isinstance(payload, dict):
        for key, value in payload.items():
            if not isinstance(key, str) or not key.strip():
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                clean[key.strip()] = value
    return {
        "messages": [{"role": "user", "content": message}],
        "user_id": user_id,
        "interaction_count": interaction_count,
        "workflow_hint": (workflow or "").strip(),
        "payload": clean,
    }


async def run_agent_stream(
    user_id: str,
    thread_id: str,
    message: str,
    model: str | None = None,
    workflow: str | None = None,
    payload: dict | None = None,
) -> AsyncIterator[dict]:
    """Exécute un run complet en streamant les événements du pipeline.

    Pipeline émis (événements réels, jamais simulés) :
      RUN_START → STATE_LOAD → USER_MESSAGE →
      (ROUTING → CONTEXT_BUILD → PROMPT_BUILD → LLM → TOOLS …) →
      ASSISTANT_MESSAGE → CHECKPOINT_SAVED → RUN_END

    Mission Assistant UI : "model" optionnel (ModelSelector) —
    sélectionne l'instance d'agent correspondante (graph.get_agent).
    workflow/payload : hint + entrée structurée du composer (§8).
    """
    agent = get_agent(model or None)
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

    input_state = _build_input(
        user_id, message, interaction_count, workflow, payload
    )

    start = time.perf_counter()

    try:
        # Timeout réel + retries BORNÉS transitoires (mission §3) :
        # asyncio.wait_for + retry policy (jamais sur validation/
        # authorization, see app/models/retry.py).
        result = await invoke_llm_with_retry(
            lambda: agent.invoke(
                input_state, config=config, context=context
            ),
            user_id=user_id,
            thread_id=thread_id,
            label=f"run_agent:{thread_id}",
            max_attempts=MODEL_RETRY_ATTEMPTS,
            timeout_seconds=AGENT_TIMEOUT_SECONDS,
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

    # V6.7 §26 : normalisation (activité + fallback du registre)
    from app.agent.middleware import (
        get_last_context,
        register_activity,
    )
    from app.agent.normalizer import normalize_response

    new_state_pre = agent.get_state(config)
    activity_pre = dict(
        (new_state_pre.values or {}).get("learning_activity") or {}
    )

    # V7 ORCHESTRATION : si le graphe parent a produit un
    # agent_response via le node RESPONSE (state.agent_response),
    # il fait FOI (contrat public complet, calculé avec l'état
    # assemblé par les nodes). Sinon → chemin historique.
    state_agent_response = (result or {}).get("agent_response") or {}

    if state_agent_response:
        agent_response = state_agent_response
    else:
        # V6.8.1 §13/§23 : enrichit le BuiltContext du registre avec
        # le résumé d'activité (copie explicite — §17) pour que le
        # contrat agrégé consommé par V7 soit complet.
        try:
            register_activity(thread_id, activity_pre)
        except Exception:
            pass
        fallback_pre = None
        search_results_pre = None
        search_used_pre = False
        try:
            last_ctx = get_last_context(thread_id)
            if last_ctx is not None:
                fallback_pre = getattr(last_ctx, "fallback", None)
                web_pre = getattr(last_ctx, "web", None)
                if web_pre is not None:
                    search_results_pre = [
                        r.model_dump() for r in web_pre.results
                    ]
                    search_used_pre = (
                        getattr(web_pre, "status", "") == "found"
                        and bool(web_pre.results)
                    )
        except Exception:
            pass

        agent_response = normalize_response(
            message=response_content,
            activity=activity_pre or None,
            search_results=search_results_pre,
            search_used=search_used_pre,
            fallback=fallback_pre,
        ).model_dump()

    yield {
        "event": "ASSISTANT_MESSAGE",
        "level": "INFO",
        "user_id": user_id,
        "thread_id": thread_id,
        "message": response_content,
        "response": response_content,
        "agent_response": agent_response,
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


def run_agent(
    user_id: str,
    thread_id: str,
    message: str,
    model: str | None = None,
    workflow: str | None = None,
    payload: dict | None = None,
) -> dict:
    """Mode synchrone (POST /api/chat) — même pipeline, sans stream.

    Mission Assistant UI : "model" optionnel (ModelSelector).
    workflow/payload : hint + entrée structurée du composer (§8).
    """
    agent = get_agent(model or None)
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

    input_state = _build_input(
        user_id, message, interaction_count, workflow, payload
    )

    # Timeout réel + retries BORNÉS transitoires (mission §3) — même
    # politique que le mode async (app/models/retry.py).
    result = invoke_llm_with_retry_sync(
        lambda: agent.invoke(input_state, config=config, context=context),
        user_id=user_id,
        thread_id=thread_id,
        label=f"run_agent_sync:{thread_id}",
        max_attempts=MODEL_RETRY_ATTEMPTS,
        timeout_seconds=AGENT_TIMEOUT_SECONDS,
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

    # V7 ORCHESTRATION : state.agent_response (node RESPONSE) fait
    # foi si présent — sinon chemin historique (registre + normalize).
    state_agent_response = (result or {}).get("agent_response") or {}

    if state_agent_response:
        agent_response = state_agent_response
    else:
        # V6.7 §26 : Response Normalizer — structures internes →
        # AgentResponse (contrat public). Le texte brut reste
        # disponible (rétrocompatibilité) ; agent_response est la
        # voie structurée du frontend.
        from app.agent.middleware import (
            get_last_context,
            register_activity,
        )
        from app.agent.normalizer import normalize_response

        activity = dict(
            (new_state.values or {}).get("learning_activity") or {}
        )
        # V6.8.1 §13/§23 : BuiltContext du registre enrichi (copie).
        try:
            register_activity(thread_id, activity)
        except Exception:
            pass
        # FallbackDecision du run courant (registre du middleware)
        fallback = None
        search_results = None
        search_used = False
        try:
            last_ctx = get_last_context(thread_id)
            if last_ctx is not None:
                fallback = getattr(last_ctx, "fallback", None)
                web = getattr(last_ctx, "web", None)
                if web is not None:
                    search_results = [
                        r.model_dump() for r in web.results
                    ]
                    search_used = (
                        getattr(web, "status", "") == "found"
                        and bool(web.results)
                    )
        except Exception:
            pass

        agent_response = normalize_response(
            message=response_content,
            activity=activity or None,
            search_results=search_results,
            search_used=search_used,
            fallback=fallback,
        ).model_dump()

    return {
        "response": response_content,
        "agent_response": agent_response,
        "user_id": user_id,
        "thread_id": thread_id,
        "interaction_count": interaction_count,
    }
