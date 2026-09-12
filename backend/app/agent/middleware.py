# Middleware V5 — observabilité tools + sécurité mémoire +
# DYNAMIC PROMPT NATIF (§8/§34/§60).
#
# Rôle réduit par rapport à V4 : l'orchestration du prompt passe
# par le mécanisme officiel @dynamic_prompt de LangChain (à la
# place d'un wrap_model_call custom qui reconstruisait tout).
# Le middleware garde uniquement :
#   1. wrap_tool_call   → observabilité TOOL_* + forçage user_id
#   2. dynamic_prompt   → prompt dynamique natif (ModelRequest :
#      request.runtime.context / request.state — plus de get_config())
#
# user_id/thread_id viennent du RUNTIME CONTEXT (context= à
# l'invoke, §4) — plus du configurable. Les tools mémoire
# gardent le forçage user_id en défense en profondeur.
import json
import time

from langchain.agents.middleware import (
    AgentMiddleware,
    ModelRequest,
    dynamic_prompt,
)

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

# Tools Learning Profile V6 (§23) : user_id forcé depuis le
# Runtime Context — le modèle ne peut pas accéder au profil
# d'apprentissage d'un autre étudiant.
LEARNING_TOOL_NAMES = {
    "get_learning_profile",
    "get_learning_topic",
    "record_learning_observation",
    "update_learning_goal",
}


def _snapshot(value, limit: int = 500) -> str:
    """Sérialise args/output de tool de façon robuste (JSON ou str)."""
    try:
        s = json.dumps(value, ensure_ascii=False, default=str)
        return s[:limit]
    except Exception:
        return str(value)[:limit]


def _ids_from_runtime(runtime) -> tuple[str, str]:
    """(user_id, thread_id) depuis un objet Runtime natif.

    §4 : user_id/thread_id sont transportés par context=
    (AgentContext) — plus de get_config()/configurable.
    """
    try:
        ctx = getattr(runtime, "context", None)
        if ctx is None:
            return "", ""
        return (
            getattr(ctx, "user_id", "") or "",
            getattr(ctx, "thread_id", "") or "",
        )
    except Exception:
        return "", ""


def _last_user_query(request: ModelRequest) -> str:
    """Dernier message humain de la requête (pour la sélection)."""
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


# ------------------------------------------------------------------
# Registre du dernier BuiltContext par thread (V6.6/V6.7).
#
# Le dynamic_prompt construit le contexte ; le Response
# Normalizer (runner) a besoin de la FallbackDecision après le
# run (ex: ambiguous → clarification). Transmettre via le state
# LangGraph imposerait un champ de plus — un registre borné par
# thread_id suffit (dernier run gagne ; purgé au-delà de 128).
# ------------------------------------------------------------------
_last_context_registry: dict[str, object] = {}
_REGISTRY_MAX = 128


def _register_context(thread_id: str, context) -> None:
    """Mémorise le dernier BuiltContext d'un thread (borné)."""
    if len(_last_context_registry) >= _REGISTRY_MAX:
        # Purge : garder les 64 entrées les plus récentes
        # (dict Python conserve l'ordre d'insertion).
        recent = list(_last_context_registry.items())[-64:]
        _last_context_registry.clear()
        _last_context_registry.update(recent)
    _last_context_registry[thread_id] = context


def get_last_context(thread_id: str):
    """Dernier BuiltContext du thread (ou None) — lu par le
    normalizer."""
    return _last_context_registry.get(thread_id)


def register_activity(thread_id: str, activity: dict) -> None:
    """V6.8.1 §13/§16/§23 — enrichit le BuiltContext du registre
    avec le résumé d'activité du run.

    Le dynamic_prompt (qui construit le BuiltContext) n'a PAS
    accès au state LangGraph (ModelRequest = messages + runtime
    uniquement) — l'activité vit dans le state, mise à jour par
    les tools pédagogiques PENDANT le run. Le runner lit le
    state POST-run et dérive la vue ici.

    §17 : DÉRIVATION EXPLICITE PAR COPIE — l'original n'est
    jamais muté ; le registre reçoit la copie enrichie. C'est
    ce BuiltContext complet que le Learning Engine V7 consommera
    (decision = decide(built_context), §23) sans reconstruction.
    """
    if not thread_id or not activity:
        return
    if activity.get("status") in (
        None,
        "",
        "idle",
        "completed",
        "abandoned",
    ):
        return
    last = _last_context_registry.get(thread_id)
    if last is None:
        return
    try:
        from app.context.schemas import ActivityContextInfo

        if getattr(last, "activity", None) is not None:
            return  # déjà enrichi (builder §13)
        enriched = last.model_copy(
            update={
                "activity": ActivityContextInfo(
                    activity_id=activity.get("activity_id", ""),
                    activity_type=activity.get("activity_type", ""),
                    status=activity.get("status", ""),
                    subject=activity.get("subject", ""),
                    topic=activity.get("topic", ""),
                    hint_level=activity.get("hint_level", 0),
                    attempts=activity.get("attempts", 0),
                )
            }
        )
        _last_context_registry[thread_id] = enriched
    except Exception:
        # Défense : l'enrichissement ne doit JAMAIS faire échouer
        # le run — le BuiltContext original reste utilisable.
        pass


@dynamic_prompt
def tutor_dynamic_prompt(request: ModelRequest) -> str:
    """Dynamic prompt officiel LangChain (§8/§34).

    Pipeline métier (§72) :
      Runtime Context (user_id) → Context Builder (sélection)
      → Prompt Builder (présentation) → prompt.

    V6.6/V6.7 : le BuiltContext construit (routing/fallback/
    web) est mis à disposition du Response Normalizer via
    _last_context_registry (clé thread_id) — le runner lit la
    décision de fallback après le run pour produire
    l'AgentResponse (clarification...). Registre borné, mémoire
    courte, thread-safe minimal (dict sous GIL, écrasement).

    Fallback (§37) : toute erreur du Context Builder est loggée
    CONTEXT_BUILD_ERROR puis le CORE PROMPT seul est utilisé —
    jamais de crash.
    """
    from app.agent.prompts import CORE_PROMPT

    user_id, thread_id = _ids_from_runtime(request.runtime)

    if not user_id:
        # Sans contexte user (startup, tests), Core seul
        return CORE_PROMPT

    query = _last_user_query(request)

    try:
        from app.context import build_context, build_system_prompt

        context = build_context(
            user_id=user_id,
            thread_id=thread_id,
            query=query,
        )
        if thread_id:
            _register_context(thread_id, context)
        return build_system_prompt(
            core_prompt=CORE_PROMPT,
            context=context,
            user_id=user_id,
            thread_id=thread_id,
        )
    except Exception as exc:
        log_event(
            "CONTEXT_BUILD_ERROR",
            level="ERROR",
            message=(
                f"Context build failed, fallback core prompt: {exc}"
            ),
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "operation": "context_build",
                "error": str(exc)[:300],
            },
        )
        return CORE_PROMPT


class ToolEventMiddleware(AgentMiddleware):
    """Intercepte l'exécution des tools (wrap_tool_call).

    Émet les événements temps réel consommés par le frontend :
      TOOL_START  → carte RUNNING (pulse + spinner)
      TOOL_END    → SUCCESS (check + durée)
      TOOL_ERROR  → ERROR (rouge + message)

    Sécurité mémoire (§47) : pour les tools mémoire longue durée,
    le paramètre user_id des args est FORCEMENT remplacé par le
    user_id réel du RUNTIME CONTEXT. Le modèle ne peut jamais
    accéder à la mémoire d'un autre utilisateur.
    """

    def wrap_tool_call(self, request, handler):
        call = request.tool_call or {}
        name = call.get("name", "unknown")
        args = call.get("args", {})

        user_id, thread_id = _ids_from_runtime(
            getattr(request, "runtime", None)
        )

        # --- Sécurité mémoire + learning (§23) : forcer le
        # user_id réel du Runtime Context ---
        if (
            name in MEMORY_TOOL_NAMES or name in LEARNING_TOOL_NAMES
        ) and user_id:
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
            duration_ms = int(
                (time.perf_counter() - start) * 1000
            )

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
            duration_ms = int(
                (time.perf_counter() - start) * 1000
            )
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
            # Ne pas crasher le run : convertir en ToolMessage
            # d'erreur pour que le LLM puisse réagir.
            from langchain_core.messages import ToolMessage

            call_id = call.get("id") or ""
            return ToolMessage(
                content=(
                    f"Erreur lors de l'exécution du tool {name} : "
                    f"{exc}"
                )[:500],
                tool_call_id=call_id,
                name=name,
            )


def build_middleware_stack() -> list:
    """Stack middleware de l'agent : dynamic prompt natif +
    observabilité/sécurité tools."""
    return [tutor_dynamic_prompt, ToolEventMiddleware()]
