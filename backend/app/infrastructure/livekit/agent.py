"""
Agent tuteur vocal — LiveKit Agents.

Ce module contient uniquement la classe TutorAgent.
Le serveur et l'entrypoint sont dans server.py.

Lancement dev :
    python -m app.infrastructure.livekit.agent
"""

from __future__ import annotations

import logging
from typing import Any

from livekit.agents import Agent, RunContext

from app.infrastructure.livekit.config import BASE_INSTRUCTIONS
from app.infrastructure.livekit.memory_tools import (
    get_user_profile,
    get_user_memory,
    search_user_memory,
    save_user_memory,
)


logger = logging.getLogger("agent-tutor.livekit")


def _configure_worker_logging() -> None:
    """Logging worker : on étouffe le bruit qui bloque l'event loop.

    Les logs LiveKit ( json ) sont formatés de façon SYNCHRONE ; sur un
    CPU shared du plan free Render, un pic de logs ( loop_monitor,
    preloading ) peut bloquer la loop audio 17 secondes d'affilée —
    entendu en prod, cassant la voix. On monte les loggers bruyants à
    ERROR et on garde WARNING+ seulement pour notre code.
    """
    for noisy in (
        "livekit.agents",
        "livekit.agents.telemetry",
        "livekit.agents.ipc",
        "livekit",
    ):
        logging.getLogger(noisy).setLevel(logging.ERROR)


# ============================================================================
# AGENT VOCAL
# ============================================================================

MEMORY_TOOLS = [
    get_user_profile,
    get_user_memory,
    search_user_memory,
    save_user_memory,
]


class TutorAgent(Agent):
    """Agent tuteur vocal — étend Agent de livekit.agents."""

    def __init__(self, instructions: str) -> None:
        super().__init__(
            instructions=instructions,
            tools=MEMORY_TOOLS,
        )

    async def on_enter(self) -> None:
        """Lance automatiquement la première réponse.

        L'agent n'attend donc pas que l'étudiant parle en premier.
        """
        await self.session.generate_reply(
            instructions="""
Commence immédiatement la conversation en français.

Présente-toi brièvement comme le tuteur vocal de l'étudiant.

Ensuite, pose une seule question simple pour savoir ce que l'étudiant
souhaite apprendre ou faire.

Ne pose pas plusieurs questions.
Ne fais pas une longue présentation.
""",
            allow_interruptions=True,
        )


# ============================================================================
# LANCEMENT (dev uniquement)
# ============================================================================

if __name__ == "__main__":
    _configure_worker_logging()
    from livekit.agents import cli
    from app.infrastructure.livekit.server import server

    cli.run_app(server)