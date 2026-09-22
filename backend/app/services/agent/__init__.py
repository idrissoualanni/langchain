# Services agent — runtime d'invocation et nodes métier du Main Graph.
#
#   orchestration.py : nodes parent (router/retrieval/fallback/context/
#                      learning/response) — minces : state → service →
#                      state update (§6 mission refactor).
#   runner.py        : invocation du graphe (run_agent/run_agent_stream,
#                      thread state/history) — I/O boundary.
#   middleware.py    : wrap_tool_call + dynamic_prompt natif.
#   normalizer.py    : normalize_response → AgentResponse.
#   prompts.py       : SYSTEM_PROMPT / CORE_PROMPT.
from app.services.agent.middleware import (
    build_middleware_stack,
    tutor_dynamic_prompt,
)
from app.services.agent.normalizer import normalize_response
from app.services.agent.orchestration import (
    context_node,
    fallback_node,
    learning_node,
    response_node,
    retrieval_node,
    route_after_router,
    router_node,
)
from app.services.agent.prompts import CORE_PROMPT, SYSTEM_PROMPT
from app.services.agent.runner import (
    get_thread_history,
    get_thread_state,
    run_agent,
    run_agent_stream,
)

__all__ = [
    "context_node",
    "fallback_node",
    "learning_node",
    "response_node",
    "retrieval_node",
    "route_after_router",
    "router_node",
    "normalize_response",
    "CORE_PROMPT",
    "SYSTEM_PROMPT",
    "get_thread_history",
    "get_thread_state",
    "run_agent",
    "run_agent_stream",
    "build_middleware_stack",
    "tutor_dynamic_prompt",
]
