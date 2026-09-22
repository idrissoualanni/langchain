# Tool Context — wrapper de subjects/tool_registry pour le Context Builder.
# Garde la séparation : le builder ne connaît que cette interface.
# FIX REVUE (blocker 1) : import depuis app.subjects.tool_registry,
# PAS app.context.tool_registry.
from app.subjects.tool_registry import get_tools_for_subject


def build_tool_context(subject_id: str | None) -> dict:
    return get_tools_for_subject(subject_id)
