"""
Point d'entrée du worker LiveKit pour Render (mode web_service).

Le plan free de Render n'a pas de type "worker" Docker : le service doit
être un web_service qui ÉCOUTE un port, sinon Render le marque inactif et
le suspend. On lance donc, dans le MÊME processus Python (512 Mo de RAM —
un second process chargant torch/onnxruntime exploserait la limite) :

    1. un mini-serveur HTTP exposant GET /healthz
    2. l'AgentServer LiveKit ( boucle asyncio partagée )

/healthz renvoie 200 seulement si le worker est enregistré auprès de
LiveKit : c'est un VRAI healthcheck. Tant que la WebSocket LiveKit n'est
pas établie, on répond 503 — Render voit le service "starting", pas
"healthy", et ne route pas de trafic vers un worker qui ne servirait
personne.

Lancement :
    RUN_AS_WORKER=1 python -m app.infrastructure.livekit.worker_main
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config import (
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET,
    LIVEKIT_HOST,
)

logger = logging.getLogger("agent-tutor.livekit.worker")


def _check_livekit_config() -> list[str]:
    """Credentials LiveKit présents ? Retourne la liste des manquants."""
    missing: list[str] = []
    if not LIVEKIT_HOST or LIVEKIT_HOST == "wss://localhost:7880":
        missing.append("LIVEKIT_URL")
    if not LIVEKIT_API_KEY or LIVEKIT_API_KEY == "devkey":
        missing.append("LIVEKIT_API_KEY")
    if not LIVEKIT_API_SECRET or LIVEKIT_API_SECRET == "devsecret":
        missing.append("LIVEKIT_API_SECRET")
    return missing


# ----------------------------------------------------------------------------
# Health HTTP — Render garde le service en vie tant qu'un port répond
# ----------------------------------------------------------------------------

# État partagé : renseigné dès que le worker est enregistré. La lecture
# est atomique (un seul writer, une seule coroutine de lecture) — pas de
# verrou nécessaire.
_worker_registered = False


def mark_registered() -> None:
    global _worker_registered
    _worker_registered = True


health_app = FastAPI(title="agent-tutor worker health", docs_url=None, redoc_url=None)


@health_app.get("/healthz")
async def healthz() -> JSONResponse:
    """200 uniquement si le worker est enregistré auprès de LiveKit."""
    status_code = 200 if _worker_registered else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "registered" if _worker_registered else "connecting",
            "worker": "tutor",
            "livekit_host": LIVEKIT_HOST,
        },
    )


# ----------------------------------------------------------------------------
# Démarrage
# ----------------------------------------------------------------------------


async def _run_health_server(port: int) -> None:
    """Serveur health (uvicorn) dans la boucle asyncio du worker."""
    import uvicorn

    config = uvicorn.Config(
        health_app,
        host="0.0.0.0",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    # handle_exit=False : SIGTERM géré par le worker LiveKit, pas par uvicorn
    # (sinon uvicorn intercepte le signal et empêche un shutdown propre).
    server.install_signal_handlers = lambda: None  # noqa: ARG005
    await server.serve()


async def _main() -> None:
    # Import ici : charger agent.py importe torch ( Silero VAD ) — ~200-300 Mo.
    # En cas de config LiveKit invalide on préfère échouer VITE avec un message
    # clair dans les logs Render plutôt qu'après ce chargement coûteux.
    missing = _check_livekit_config()
    if missing:
        logger.error(
            "Configuration LiveKit INCOMPLÈTE — variables manquantes : %s. "
            "Le worker ne peut pas s'enregistrer. "
            "Définissez-les dans le dashboard Render.",
            ", ".join(missing),
        )
        sys.exit(1)

    from app.infrastructure.livekit.agent import server  # noqa: PLC0415

    logger.info(
        "Démarrage worker tuteur | host=%s | agent=tutor",
        LIVEKIT_HOST,
    )

    port = int(os.getenv("PORT", "10000"))

    # AgentServer.run() est une coroutine : on la lance comme tâche, le
    # health server en parallèle, dans la MÊME boucle ( un processus ).
    health_task = asyncio.create_task(_run_health_server(port))
    # _connecting est remis à False et _connection_failed à False quand la
    # WebSocket LiveKit est établie et le worker enregistré.
    watchdog_task = asyncio.create_task(_registration_watchdog(server))

    try:
        # run() ne revient que sur shutdown — bloquant en fonctionnement normal.
        await server.run()
    finally:
        health_task.cancel()
        watchdog_task.cancel()


async def _registration_watchdog(server) -> None:
    """Marque le worker sain ( 200 sur /healthz ) dès qu'il est enregistré.

    AgentServer expose _connecting ( True pendant la négociation WebSocket )
    et _connection_failed ( True si l'enregistrement a échoué ). On sonde
    ces attributs jusqu'à ce que la connexion soit établie.

    Sans ça, /healthz resterait 503 pour toujours : server.run() ne rend
    la main qu'à l'arrêt, on ne pourrait jamais savoir qu'il est prêt.
    """
    while True:
        try:
            connecting = getattr(server, "_connecting", False)
            failed = getattr(server, "_connection_failed", False)
        except Exception:  # noqa: BLE001 — attribut interne, jamais fatal
            await asyncio.sleep(2)
            continue

        if failed:
            logger.error(
                "ÉCHEC de l'enregistrement du worker auprès de LiveKit "
                "( host=%s ). /healthz reste 503 — vérifiez LIVEKIT_URL et "
                "les credentials API.",
                LIVEKIT_HOST,
            )
            return

        # Enregistré : la négociation est terminée et n'a pas échoué.
        if not connecting:
            mark_registered()
            logger.info("Worker enregistré auprès de LiveKit — /healthz → 200")
            return

        await asyncio.sleep(2)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    # Réutilise l'étouffage des logs LiveKit du worker ( event loop saturée
    # en prod par le logging synchrone de la lib ).
    from app.infrastructure.livekit.agent import _configure_worker_logging

    _configure_worker_logging()

    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
