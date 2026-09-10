import json
import time

from langchain.agents.middleware import AgentMiddleware

from app.logging.events import log_event

MEMORY_TOOL_NAMES = {
    "get_user_profile",
    "update_user_profile",
    "get_user_memory",
    "save_user_memory",
    "update_user_memory",
    "delete_user_memory",
    "search_user_memory",
}


def _snapshot(value, limit: int = 500) -> str:
    """Sérialise args/output de tool de façon robuste (JSON ou str)."""
    try:
        s = json.dumps(value, ensure_ascii=False, default=str)
        return s[:limit]
    except Exception:
        return str(value)[:limit]


def _current_ids() -> tuple[str, str]:
    """(user_id, thread_id) depuis la config LangGraph courante."""
    try:
        from langgraph.config import get_config

        cfg = get_config() or {}
        configurable = cfg.get("configurable") or {}
        return (
            configurable.get("user_id", ""),
            configurable.get("thread_id", ""),
        )
    except Exception:
        return "", ""


def _last_user_query(request) -> str:
    """Dernier message humain de la requête (pour la sélection mémoire)."""
    try:
        from langchain_core.messages import HumanMessage

        msgs = [
            m
            for m in (request.messages or [])
            if isinstance(m, HumanMessage)
        ]
        if not msgs:
            return ""
        content = msgs[-1].content
        if isinstance(content, str):
            return content
        return str(content)
    except Exception:
        return ""


class ToolEventMiddleware(AgentMiddleware):
    """Intercepte chaque exécution de tool (wrap_tool_call).

    Émet les événements temps réel consommés par le frontend :
      TOOL_START  → carte tool RUNNING (pulse + spinner)
      TOOL_END    → SUCCESS (check + durée)
      TOOL_ERROR  → ERROR (rouge + message)

    Sécurité mémoire : pour les tools de mémoire longue durée,
    le paramètre user_id des args est FORCEMENT remplacé par le
    user_id réel de la config LangGraph. Le modèle ne peut donc
    jamais accéder à la mémoire d'un autre utilisateur, même
    s'il fournit un autre user_id dans les arguments du tool.
    """

    def wrap_tool_call(self, request, handler):
        call = request.tool_call or {}
        name = call.get("name", "unknown")
        args = call.get("args", {})

        user_id, thread_id = _current_ids()

        # --- Sécurité mémoire : forcer le user_id réel ---
        if name in MEMORY_TOOL_NAMES and user_id:
            forced_args = {**args, "user_id": user_id}
            call = {**call, "args": forced_args}
            request = request.override(tool_call=call)
            args = forced_args

        log_event(
            "TOOL_START",
            message=f"Tool {name} started",
            user_id=user_id,
            thread_id=thread_id,
            tool_name=name,
            extra={"input": _snapshot(args)},
        )

        start = time.perf_counter()

        try:
            result = handler(request)
            duration_ms = int((time.perf_counter() - start) * 1000)

            output = getattr(result, "content", result)
            log_event(
                "TOOL_END",
                message=f"Tool {name} completed in {duration_ms}ms",
                user_id=user_id,
                thread_id=thread_id,
                tool_name=name,
                extra={
                    "output": _snapshot(output),
                    "duration_ms": duration_ms,
                },
            )
            return result

        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            log_event(
                "TOOL_ERROR",
                level="ERROR",
                message=f"Tool {name} failed: {exc}",
                user_id=user_id,
                thread_id=thread_id,
                tool_name=name,
                extra={
                    "error": str(exc)[:300],
                    "duration_ms": duration_ms,
                },
            )
            # Ne pas crasher le run : convertir en ToolMessage d'erreur
            # pour que le LLM puisse réagir (comportement ToolNode).
            # L'exception ne remonte pas — l'agent poursuit la conversation.
            from langchain_core.messages import ToolMessage

            call_id = call.get("id") or ""
            return ToolMessage(
                content=(
                    f"Erreur lors de l'exécution du tool {name} : {exc}"
                )[:500],
                tool_call_id=call_id,
                name=name,
            )

    def wrap_model_call(self, request, handler):
        """Pipeline V4 : ROUTING → CONTEXT → PROMPT dynamique.

        Le system prompt de l'agent (Core Prompt) est remplacé par
        Core + MATIÈRE + KNOWLEDGE + USER + THREAD, assemblés par le
        Context/Prompt Builder. Observabilité complète (ROUTING_*,
        CONTEXT_BUILD_*, SUBJECT_CONTEXT_SELECTED, KNOWLEDGE_SELECTED,
        TOOLS_SELECTED, PROMPT_BUILD) émise par le package app/context.
        Fallback : Core seul si le builder échoue (jamais de crash).
        """
        user_id, thread_id = _current_ids()

        if user_id:
            query = _last_user_query(request)

            # Prompt de base = Core Prompt de l'agent
            base_prompt = (
                request.system_prompt
                or (
                    request.system_message.content
                    if request.system_message
                    else ""
                )
                or ""
            )

            # Le base_prompt contient déjà le Core Prompt (créé avec
            # l'agent). On REMPLACE par Core + contextes dynamiques :
            # on retire un éventuel USER CONTEXT ou MATIÈRE déjà
            # injectés au tour précédent pour ne jamais dupliquer.
            core = base_prompt.split("## USER CONTEXT")[0].strip()
            core = core.split("## MATIÈRE")[0].strip()

            try:
                from app.agent.prompts import CORE_PROMPT
                from app.context import build_context, build_system_prompt

                context = build_context(
                    user_id=user_id,
                    thread_id=thread_id,
                    query=query,
                )
                new_prompt = build_system_prompt(
                    core_prompt=CORE_PROMPT,
                    context=context,
                    user_id=user_id,
                    thread_id=thread_id,
                )
            except Exception as exc:
                # Le context builder ne doit JAMAIS casser un appel LLM
                log_event(
                    "CONTEXT_BUILD_ERROR",
                    level="ERROR",
                    message=f"Context build failed, fallback core prompt: {exc}",
                    user_id=user_id,
                    thread_id=thread_id,
                    extra={"operation": "context_build", "error": str(exc)[:300]},
                )
                new_prompt = core

            request = request.override(
                system_prompt=new_prompt,
            )

        return handler(request)
