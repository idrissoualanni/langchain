# AGENDA node du Main Graph — workflow "agenda" ( MCP Calendar §40 ).
#
# Quand WORKFLOW_ROUTER decide "agenda" ( hint du composer @agenda ), CE
# node orchestre la gestion calendrier :
#
#   1. charge les tools MCP du serveur "agenda" ( get_mcp_tools — c'etait
#      le chainon manquant : la couche MCP etait ecrite mais n'etait
#      appelee par PERSONNE ).
#   2. instancie un mini-agent ( create_agent ) avec ces tools,
#   3. laisse le LLM decider quel tool appeler ( check_availability /
#      create_event / list_events ) selon la demande naturelle,
#   4. rend le contrat AgendaResult ( §8 ) pour la chaine principale.
#
# Backend : API Google Calendar reelle ( OAuth2 ) si configure, sinon store
# JSON — le node ne sait pas lequel, c'est le contrat MCP qui le garantit.
#
# Fail-safe ( §15 ) : une erreur MCP ( serveur KO, OAuth absent ) est rendue
# en AgendaResult(status="error") — le Main Graph ne voit JAMAIS d'exception.
# Scoping ( §40 ) : les tools agenda ne sont exposes QU'ici, jamais au Main
# Agent global.
from __future__ import annotations

from typing import Any

from app.logging.events import log_event

_AGENDA_SYSTEM_PROMPT = """Tu es l'assistant agenda de l'utilisateur. \
Tu disposes de trois outils :
- check_availability(start, end) : l'utilisateur est-il libre sur le créneau ?
- create_event(title, start, end) : créer un événement (uniquement si la \
demande est explicite et le créneau confirmé libre).
- list_events(days) : lister les événements à venir.

Règles STRICTES :
1. Les dates sont en format ISO ( ex: "2026-09-25T14:00:00" ). Convertis les \
expressions naturelles ("demain 14h", "lundi prochain") en ISO avant d'appeler \
un outil. Si la date est ambiguë ou manquante, DEMANDE clarification — \
n'invente JAMAIS une date.
2. N'invente JAMAIS un événement. create_event n'est appelé que si \
l'utilisateur a clairement demandé de créer quelque chose.
3. Après chaque appel d'outil, réponds en français, de façon concise et \
lisible ( formulations complètes, pas de style télégraphique ).
4. Si un outil retourne une erreur, rapporte-la clairement à l'utilisateur \
sans réessayer en boucle.
"""


async def agenda_node(state, config=None) -> dict[str, Any]:
    """AGENDA — exécute le mini-agent agenda + tools MCP ( §40 ).

    Entrée : la demande vient du canal intake.query ( ou du dernier
    message humain ). C'est du LANGAGE NATUREL — le LLM décide lui-même
    quel tool appeler, le node ne parse pas les dates.

    Sortie : workflow_result ( AgendaResult §8 ). Les tools MCP sont
    chargés via get_mcp_tools("agenda") — résolution registry + scoping
    §40 ( seules les serveurs dont allowed_workflows contient "agenda" ).
    """
    from app.infrastructure.mcp.toolset import get_mcp_tools
    from app.schemas.workflow import AgendaResult

    intake = (state or {}).get("intake") or {}
    query = intake.get("query") if isinstance(intake, dict) else ""
    if not query and isinstance(state, dict):
        query = state.get("query") or ""

    user_id = (state or {}).get("user_id") or ""
    thread_id = ""
    if config:
        thread_id = (
            config.get("configurable") or {}
        ).get("thread_id") or ""

    log_event(
        "AGENDA_NODE_START",
        message=f"Agenda workflow start | query_chars={len(query)}",
        user_id=user_id,
        thread_id=thread_id,
        extra={"operation": "agenda_node"},
    )

    try:
        # 1. Tools MCP — résolution + scoping §40. Échec isolé : liste
        # vide ( jamais de crash du node ).
        tools = await get_mcp_tools("agenda")

        if not tools:
            # Soit aucun serveur agenda activé ( MCP_ENABLED_SERVERS ),
            # soit le serveur a planté au démarrage. Détail pour l'obs.
            return {
                "workflow_result": AgendaResult(
                    workflow="agenda",
                    status="error",
                    message=(
                        "Le serveur d'agenda est indisponible "
                        "( couche MCP désactivée ou serveur en échec ) "
                        "— réessayez plus tard."
                    ),
                ).model_dump()
            }

        # 2. Mini-agent — boucle LLM + tools ( create_agent, comme la
        #    chaîne principale mais avec un scope strict ). On résout
        #    le modèle défaut ( tools MCP en remplacement de all_tools ).
        from app.graph.main.graph import _resolve_llm_and_tools

        model, _ignored_tools = _resolve_llm_and_tools()

        from langgraph.prebuilt import create_agent

        agent = create_agent(model, tools=tools, prompt=_AGENDA_SYSTEM_PROMPT)
        result = await agent.ainvoke({"messages": [("user", query)]})

        # 3. Réponse : dernier message de l'agent.
        messages = result.get("messages", []) if isinstance(result, dict) else []
        answer = ""
        for msg in reversed(messages):
            content = getattr(msg, "content", None)
            if isinstance(content, str) and content.strip():
                answer = content.strip()
                break

        # 4. Détecte l'outil utilisé ( première tool call ) pour le contrat.
        action = ""
        for msg in messages:
            tool_calls = getattr(msg, "tool_calls", None)
            if tool_calls:
                action = str(tool_calls[0].get("name", ""))
                break

        status: str = "ok" if answer else "partial"

        log_event(
            "AGENDA_NODE",
            message=(
                f"Agenda workflow run | status={status} "
                f"| action={action} | tools={len(tools)}"
            ),
            user_id=user_id,
            thread_id=thread_id,
            extra={
                "operation": "agenda_node",
                "status": status,
                "action": action,
                "tool_count": len(tools),
            },
        )

        return {
            "workflow_result": AgendaResult(
                workflow="agenda",
                status=status,
                message=answer or "Agenda traité sans réponse.",
                action=action,
                answer=answer,
            ).model_dump()
        }

    except Exception as exc:  # noqa: BLE001 — isolation du run ( §15 )
        log_event(
            "AGENDA_NODE_ERROR",
            level="ERROR",
            message=f"Agenda workflow failed: {exc}",
            user_id=user_id,
            thread_id=thread_id,
            extra={"operation": "agenda_node"},
        )
        return {
            "workflow_result": AgendaResult(
                workflow="agenda",
                status="error",
                message=f"Agenda en échec : {exc}",
            ).model_dump()
        }


def route_after_agenda(state) -> str:
    """Après AGENDA : retour TOUJOURS sur la chaîne principale."""
    return "context"


__all__ = ["agenda_node", "route_after_agenda"]
