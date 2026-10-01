"""Point d'entrée LiveKit Cloud — agent tuteur vocal.

Ce module est importé par `lk agent create/deploy` et DOIT exposer :
- `server = AgentServer()` au niveau MODULE (le CLI cherche le symbole
  dans le module, pas dans une fonction) ;
- `server.rtc_session()(entrypoint)` SANS `agent_name=` : l'identité de
  l'agent vient de la variable d'environnement `LIVEKIT_AGENT_NAME`
  (secret injecté par le CLI depuis `.env.local`), source unique de vérité.

⚠️ ORDRE IMPÉRATIF : `server.rtc_session()(entrypoint)` doit être exécuté
APRÈS la définition de `entrypoint`, sinon `NameError` au chargement du
module → le conteneur part en CrashLoop.
"""

from __future__ import annotations

import asyncio
import logging
import os

from livekit.agents import Agent, AgentServer, JobContext, RunContext

from config import GREETING, build_system_instructions, get_agent_config
from session_factory import (
    PipelineBuildError,
    build_session,
    resolve_user_id_from_job,
)

logger = logging.getLogger("agent-tutor.livekit")

os.environ.setdefault("LIVEKIT_LOG_LEVEL", "info")
logging.basicConfig(
    level=os.getenv("LIVEKIT_LOG_LEVEL", "info").upper(),
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)


# ============================================================================
# AGENT
# ============================================================================

class TutorAgent(Agent):
    """Tuteur vocal francophone : STT → LLM → TTS."""

    async def on_enter(self) -> None:
        """Accueil de l'étudiant dès l'ouverture du micro."""
        await self.session.say(GREETING)


# ============================================================================
# SERVEUR — niveau module, REQUIS par le CLI LiveKit
# ============================================================================

server = AgentServer(num_idle_processes=0)

# ⚠️ L'enregistrement de la session se fait PLUS BAS, après la définition de
# `entrypoint` : l'appel est exécuté au moment de l'import du module, donc
# `entrypoint` doit déjà exister (sinon NameError → CrashLoop).


# ============================================================================
# ENTRYPOINT
# ============================================================================

async def entrypoint(ctx: JobContext) -> None:
    """Connecte l'agent à la room et démarre la session vocale."""
    logger.info("Job reçu — room=%s", ctx.room.name)

    config = get_agent_config()
    logger.info("Pipeline : %s", config.to_dict())

    # Construction AVANT ctx.connect() : une configuration invalide doit
    # faire échouer le job avec un log explicite, pas un agent muet en salle.
    try:
        session = build_session(config)
    except PipelineBuildError as exc:
        logger.error("Pipeline vocal inutilisable : %s", exc)
        return

    user_id = resolve_user_id_from_job(ctx.job.metadata, ctx.room.name)
    logger.info("user_id résolu : %s", user_id or "(aucun)")

    instructions = build_system_instructions()

    try:
        await ctx.connect()
        logger.info("Connecté à la room %s", ctx.room.name)

        await session.start(
            agent=TutorAgent(instructions=instructions),
            room=ctx.room,
        )
        logger.info("Session vocale démarrée")
    except Exception as exc:  # noqa: BLE001 — on veut un log, pas un traceback muet
        logger.exception("Erreur fatale pendant la session : %s", exc)
        return

    # Maintient le job vivant jusqu'à la fin de la room.
    await asyncio.Future()


# ============================================================================
# ENREGISTREMENT DE LA SESSION RTC
# ============================================================================

# SANS agent_name= : le nom vient de LIVEKIT_AGENT_NAME (secret injecté par le
# CLI LiveKit depuis .env.local, cf. livekit.agents.worker.py). Passer le nom
# ici créerait une seconde source de vérité divergente du dispatch API.
server.rtc_session()(entrypoint)


if __name__ == "__main__":
    from livekit.agents import cli

    cli.run_app(server)
