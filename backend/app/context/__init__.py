# Package context — Context Engineering (V4)
#
#   router           → subject/topic/status d'une question
#   build_context()  → sélectionne les infos pertinentes multi-sources
#   prompt_builder   → assemble le system prompt final
#
# Architecture V4 (§29) :
#   ROUTER + SUBJECT CONFIG + KNOWLEDGE + TOOLS + USER MEMORY
#   + THREAD STATE (+ LEARNING réservé V5+) → BUILDER → PROMPT → MODEL
from app.context.builder import (
    build_context,
    build_system_prompt,
    build_thread_context,
    build_user_context,
)
from app.context.prompt_builder import build_system_prompt  # noqa: F811
from app.context.router import route_subject

__all__ = [
    "build_context",
    "build_system_prompt",
    "build_thread_context",
    "build_user_context",
    "route_subject",
]
