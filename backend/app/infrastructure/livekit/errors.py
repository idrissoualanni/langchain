"""Gestion d'erreurs LiveKit — classification, journalisation, fallbacks.

Ce module vit DANS le package livekit : toute la robustesse "erreur" du
pipeline vocal est localisée ici ( et nulle part ailleurs ).

Chaque erreur est :
  1. CLASSÉE   → code lisible ( inference_invalid_model, rtc_disconnected, ... )
  2. LOGGÉE    → logger structuré + log_event ( visible dans /api/logs SSE )
  3. RÉPONDUE  → message vocal court à l'étudiant quand c'est possible
  4. LIMITÉE   → garde anti-boucle : au-delà d'un seuil d'erreurs
                 irrécupérables, on stoppe le job proprement plutôt que
                 de faire tourner un agent mort ( qui consomme de
                 l'inference et laisse l'étudiant face au silence ).

Points d'accroche réels vérifiés contre livekit-agents 1.8.x :
  - AgentSession émet "error" ( ErrorEvent : error=LLMError|STTError|TTSError,
    source=stt|llm|tts ) depuis voice/agent_activity.py::_on_error ;
  - AgentSession émet "close" ( CloseEvent : error | None, reason=CloseReason )
    quand une erreur NON récupérable ferme la session — c'est là que le
    piège historique se matérialisait : l'agent devenait muet en silence ;
  - Room (livekit.rtc) émet "reconnecting" / "disconnected" → détection RTC.

Le piège historique : une erreur Inference ( ex : modèle inexistant dans
le catalogue ) se déclenche AU PREMIER TOUR DE PAROLE, dans le job
subprocess — invisible dans les logs du service Render. Ce module rend
ces erreurs visibles et actionnables.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger("agent-tutor.livekit.errors")


# ============================================================================
# CODES — source unique de vérité pour le frontend ( livekitErrors.ts )
# ============================================================================

CODE_INFERENCE_UNAVAILABLE = "inference_unavailable"   # réseau/gateway injoignable
CODE_INFERENCE_AUTH = "inference_auth"                 # credentials / projet invalide
CODE_INFERENCE_MODEL = "inference_invalid_model"       # modèle absent du catalogue
CODE_INFERENCE_RATE_LIMIT = "inference_rate_limited"   # quota / 429
CODE_RTC_DISCONNECTED = "rtc_disconnected"             # WebSocket room perdue
CODE_JOB_SHUTDOWN = "job_shutdown"                     # arrêt normal du job
CODE_INTERNAL = "internal_error"                       # tout le reste

#: messages vocaux courts — formulés pour être lus par le TTS.
_SPOKEN_MESSAGES: dict[str, str] = {
    CODE_INFERENCE_UNAVAILABLE: (
        "Je rencontre un problème de connexion à mes services vocaux. "
        "Réessayons dans quelques instants."
    ),
    CODE_INFERENCE_AUTH: (
        "Mes services vocaux refusent ma connexion. "
        "Préviens l'administrateur, je dois m'arrêter."
    ),
    CODE_INFERENCE_MODEL: (
        "Un problème de configuration m'empêche de traiter la voix. "
        "Je préfère m'arrêter plutôt que rester muet."
    ),
    CODE_INFERENCE_RATE_LIMIT: (
        "Trop de demandes en ce moment — attends quelques secondes et repose ta question."
    ),
    CODE_RTC_DISCONNECTED: (
        "La connexion à la salle a été perdue. Je termine cette session."
    ),
    CODE_INTERNAL: (
        "Une erreur interne vient de se produire. "
        "Si cela persiste, termine la session et recommence."
    ),
}


def spoken_message(code: str) -> str:
    """Message vocal associé à un code d'erreur (pour annonce directe)."""
    return _SPOKEN_MESSAGES.get(code, _SPOKEN_MESSAGES[CODE_INTERNAL])


# ============================================================================
# CLASSIFICATION
# ============================================================================

def _http_status_of(exc: BaseException) -> int | None:
    """Extrait un status HTTP porté par une exception API LiveKit."""
    for attr in ("status_code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    return None


def classify_exception(exc: BaseException) -> tuple[str, bool]:
    """Classe une exception LiveKit en ( code, recoverable ).

    Recoverable = l'étudiant peut continuer ( on loggue, on prévient,
    on ne tue pas le job ). Non-récupérable = le pipeline est cassé,
    maintenir la session ouverte = agent muet = pire UX.

    La détection est typée ET textuelle : les erreurs Inference remontent
    souvent comme des RuntimeError/aiohttp.ClientError dont seul le
    message indique la cause ( "invalid model", "401 unauthorized", ... ).
    """
    # Import local : livekit.agents coûte ~200 Mo ( torch VAD ) — on ne
    # charge ces types que quand une erreur survient réellement.
    try:
        from livekit.agents import APIError  # noqa: PLC0415
    except Exception:  # pragma: no cover - environnement sans livekit
        APIError = None  # type: ignore[assignment]

    # Les wrappers LLMError/STTError/TTSError de la lib portent déjà un
    # champ `recoverable` et l'exception racine dans `.error`.
    inner = getattr(exc, "error", None)
    if isinstance(inner, BaseException) and inner is not exc:
        # Le CODE se détermine sur la racine ( plus précis ) ; la
        # sémantique recoverable de la lib est conservée en priorité.
        code, _ = classify_exception(inner)
        return code, bool(getattr(exc, "recoverable", False))

    msg = str(exc).lower()

    if APIError is not None and isinstance(exc, APIError):
        status = _http_status_of(exc)
        if status in (401, 403) or "unauthorized" in msg or "api key" in msg:
            return CODE_INFERENCE_AUTH, False
        if status == 429 or "rate" in msg or "quota" in msg:
            return CODE_INFERENCE_RATE_LIMIT, True
        if "model" in msg and (
            "invalid" in msg or "not found" in msg or "unsupported" in msg
            or "unknown" in msg
        ):
            return CODE_INFERENCE_MODEL, False
        if getattr(exc, "retryable", False):
            return CODE_INFERENCE_UNAVAILABLE, True
        return CODE_INTERNAL, False

    # Erreurs réseau / DNS ( gateway injoignable, cold start Render )
    if any(k in msg for k in (
        "cannot connect to host", "timed out", "timeout", "ssl",
        "dnslookup", "name or service not known", "network",
        "connection refused", "server disconnected",
    )):
        return CODE_INFERENCE_UNAVAILABLE, True
    if "invalid model" in msg or "unsupported model" in msg or "unknown model" in msg:
        return CODE_INFERENCE_MODEL, False
    if "401" in msg or "unauthorized" in msg:
        return CODE_INFERENCE_AUTH, False
    if "429" in msg or "rate limit" in msg:
        return CODE_INFERENCE_RATE_LIMIT, True
    return CODE_INTERNAL, False


# ============================================================================
# GARDE ANTI-BOUCLE
# ============================================================================


@dataclass
class ErrorGuard:
    """Limite les erreurs par job pour éviter un agent zombie.

    - erreurs récupérables : tolérées jusqu'à `max_recoverable` ;
      au-delà, on considère le pipeline comme instable → shutdown.
    - erreurs non récupérables : LA première suffit ( modèle invalide,
      auth cassée ) — attendre la deuxième ne fait que gaspiller de
      l'inference et laisser l'étudiant dans le silence.
    """

    max_recoverable: int = 5
    #: fenêtre ( s ) pendant laquelle on agrège ; hors fenêtre on repart de zéro
    window_s: float = 120.0

    _events: list[tuple[float, str, bool]] = field(default_factory=list)

    def record(self, code: str, recoverable: bool) -> bool:
        """Enregistre une erreur. Retourne True si le job doit s'arrêter."""
        try:
            now = asyncio.get_running_loop().time()
        except RuntimeError:
            now = 0.0  # hors loop ( tests ) : pas de fenêtrage temporel
        self._events = [e for e in self._events if now - e[0] < self.window_s]
        self._events.append((now, code, recoverable))

        if not recoverable:
            return True
        n_recov = sum(1 for _, _, r in self._events if r)
        return n_recov > self.max_recoverable

    @property
    def history(self) -> list[str]:
        return [code for _, code, _ in self._events]


# ============================================================================
# PUBLICATION DES ERREURS ( bus de logs → SSE /api/logs → frontend )
# ============================================================================


def publish_error(
    *,
    room_name: str,
    user_id: str,
    code: str,
    recoverable: bool,
    source: str,
    detail: str,
) -> None:
    """Publique LIVEKIT_ERROR dans le bus applicatif ( visible via /api/logs ).

    Ne lève JAMAIS : le bus de log doit être incapable de casser le worker.
    """
    message = (
        f"Erreur {source} | room={room_name} | code={code} "
        f"| recoverable={recoverable} | {detail}"
    )[:400]
    level = "WARNING" if recoverable else "ERROR"
    logger.log(logging.WARNING if recoverable else logging.ERROR, message)
    try:
        from app.logging.events import log_event  # noqa: PLC0415

        log_event(
            "LIVEKIT_ERROR",
            level=level,
            message=message,
            user_id=user_id,
            extra={"room": room_name, "code": code, "source": source},
        )
    except Exception:  # noqa: BLE001 — jamais fatal
        pass


# ============================================================================
# POINT D'ENTRÉE SESSION
# ============================================================================

OnFatal = Callable[[str], Awaitable[None]]


def attach_error_handler(
    session: Any,
    *,
    guard: ErrorGuard,
    room: Any | None,
    room_name: str,
    user_id: str,
    on_fatal: OnFatal,
) -> None:
    """Abonne la gestion d'erreurs LiveKit sur une AgentSession (+ sa Room).

    Trois accroches, toutes défensives (noms d'événements vérifiés contre
    livekit-agents 1.8.x) :

    1. session "error"  → ErrorEvent(error=LLMError|STTError|TTSError) :
       classification, publication, annonce orale unique par code si
       récupérable, sinon décision de la garde → on_fatal.
    2. session "close"  → CloseEvent(error, reason) : c'est LE signal qui
       manquait — une erreur irrécupérable ferme la session via la lib ;
       sans handler, l'étudiant ne voit qu'un micro mort. Ici on publie
       l'erreur racine avec son code et on délègue l'arrêt propre.
    3. room "reconnecting"/"disconnected" → CODE_RTC_DISCONNECTED (log
       seulement : la lib reconnecte seule, un shutdown serait pire).

    Args:
        session: AgentSession construit ( avant ou après start — .on
            fonctionne aux deux moments ).
        guard: compteur anti-boucle, un par job.
        room: ctx.room ( optionnel ) pour la surveillance RTC.
        room_name / user_id: contexte des logs publiés.
        on_fatal: coroutine appelée quand la garde ordonne l'arrêt
            ( typiquement : annonce vocale + ctx.shutdown ).
    """
    announced: set[str] = set()

    async def _on_error(ev: Any) -> None:
        exc = getattr(ev, "error", ev)
        code, recoverable = classify_exception(exc)
        must_stop = guard.record(code, recoverable)

        src_obj = getattr(ev, "source", None)
        source = (
            getattr(exc, "label", None)
            or type(src_obj).__name__.lower().strip("_")
            or "?"
        )
        publish_error(
            room_name=room_name,
            user_id=user_id,
            code=code,
            recoverable=recoverable,
            source=str(source),
            detail=f"{type(exc).__name__}: {exc}",
        )

        if must_stop:
            try:
                await on_fatal(code)
            except Exception as fatal_exc:  # noqa: BLE001
                logger.warning("on_fatal échoué : %s", fatal_exc)
            return

        # Erreur récupérable mais gênante : on prévient oralement UNE
        # seule fois par code et par job ( sinon chaque balbutiement STT
        # ferait parler l'agent en boucle ). Le rate-limit est volontairement
        # silencieux : la lib réessaie seule, l'étudiant n'a rien à savoir.
        if code != CODE_INFERENCE_RATE_LIMIT and code not in announced:
            announced.add(code)
            try:
                await session.say(spoken_message(code), allow_interruptions=True)
            except Exception:  # noqa: BLE001 — session déjà fermée, pas grave
                pass

    async def _on_close(ev: Any) -> None:
        exc = getattr(ev, "error", None)
        if exc is None:
            return  # fermeture propre ( fin de job, utilisateur parti )
        code, recoverable = classify_exception(exc)
        publish_error(
            room_name=room_name,
            user_id=user_id,
            code=code,
            recoverable=recoverable,
            source="session",
            detail=(
                f"session fermée par la lib ({getattr(ev, 'reason', '?')}) — "
                f"{type(exc).__name__}: {exc}"
            ),
        )
        # Filet de sécurité : si le handler "error" n'a pas pu ordonner
        # l'arrêt ( erreur arrivée entre les deux events ), on le fait ici.
        if not recoverable:
            try:
                await on_fatal(code)
            except Exception as fatal_exc:  # noqa: BLE001
                logger.warning("on_fatal(close) échoué : %s", fatal_exc)

    attached = 0
    for event_name, handler in (("error", _on_error), ("close", _on_close)):
        try:
            session.on(event_name, handler)
            attached += 1
        except Exception as exc:  # noqa: BLE001 — API changée entre versions
            logger.warning(
                "Impossible d'attacher le handler '%s' sur AgentSession : %s",
                event_name, exc,
            )

    if room is not None:
        def _on_rtc(*_args: Any, **_kw: Any) -> None:
            publish_error(
                room_name=room_name,
                user_id=user_id,
                code=CODE_RTC_DISCONNECTED,
                recoverable=True,
                source="room",
                detail="WebSocket room instable — reconnexion en cours",
            )

        for event_name in ("reconnecting", "disconnected"):
            try:
                room.on(event_name, _on_rtc)
            except Exception as exc:  # noqa: BLE001
                logger.debug("handler RTC '%s' non attaché : %s", event_name, exc)

    if attached == 0:  # pragma: no cover — version incompatible
        logger.error(
            "AUCUN handler d'erreur LiveKit attaché — l'agent redevient "
            "'silencieux' en cas de panne Inference. Vérifiez la version "
            "de livekit-agents."
        )
