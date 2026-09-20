# Retry borné (mission §14) — invocation LLM/agent.
#
# Les retries sont RÉSERVÉS aux erreurs transitoires (réseau, timeout,
# rate-limit temporaire) : max_attempts borné (2-3), observable
# (log_event LLM_RETRY), JAMAIS sur erreurs de validation /
# authorisation / sécurité (elles remontent immédiatement).
from __future__ import annotations

import asyncio

from app.config import MODEL_RETRY_ATTEMPTS, MODEL_REQUEST_TIMEOUT_SECONDS
from app.logging.events import log_event

_RETRYABLE_STATUS = (429, 500, 502, 503, 504)
_RETRYABLE_NAMES = {
    "TimeoutException",
    "ConnectError",
    "ConnectTimeout",
    "ReadTimeout",
    "WriteTimeout",
    "PoolTimeout",
    "RemoteProtocolError",
    "RequestError",
}


def is_transient_error(exc: BaseException) -> bool:
    """Erreur transitoire ? (réseau/timeout/429/5xx temporaire).

    Retourne False pour toute erreur de validation, authorization ou
    sécurité — un retry n'est jamais tenté sur ces classes (@14).
    """
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return True
    if isinstance(exc, (ConnectionError, BrokenPipeError)):
        return True
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and status in _RETRYABLE_STATUS:
        return True
    if type(exc).__name__ in _RETRYABLE_NAMES:
        return True
    try:
        import httpx

        if isinstance(exc, httpx.TransportError):
            return True
    except ImportError:
        pass
    try:
        import requests

        if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
            return True
    except ImportError:
        pass
    return False


def _retry_delay(attempt: int, base: float = 0.5) -> float:
    """Backoff court, borné à 2s."""
    return min(base * (attempt - 1) + 0.1, 2.0)


async def invoke_llm_with_retry(
    call,
    *,
    user_id: str = "",
    thread_id: str = "",
    label: str = "llm-invoke",
    max_attempts: int = MODEL_RETRY_ATTEMPTS,
    timeout_seconds: float | None = MODEL_REQUEST_TIMEOUT_SECONDS,
):
    """Invoque call() (synchrone) dans un executor avec timeout réel.

    Retries BORNÉS réservés aux erreurs transitoires ; toute autre
    erreur est levée immédiatement (jamais de retry).
    """
    attempt = 0
    loop = asyncio.get_running_loop()
    while True:
        attempt += 1
        future = loop.run_in_executor(None, call)
        try:
            return await asyncio.wait_for(
                future, timeout=timeout_seconds
            )
        except Exception as exc:
            future.cancel()
            if attempt >= max_attempts or not is_transient_error(exc):
                raise
            log_event(
                "LLM_RETRY",
                level="WARNING",
                message=(
                    f"{label} retry {attempt}/{max_attempts} "
                    f"(transitoire)"
                ),
                user_id=user_id,
                thread_id=thread_id,
                extra={"operation": "retry", "label": label},
            )
            await asyncio.sleep(_retry_delay(attempt))


def invoke_llm_with_retry_sync(
    call,
    *,
    user_id: str = "",
    thread_id: str = "",
    label: str = "llm-invoke",
    max_attempts: int = MODEL_RETRY_ATTEMPTS,
    timeout_seconds: float | None = MODEL_REQUEST_TIMEOUT_SECONDS,
):
    """Version synchrone (POST /api/chat) — même sémantique de retry."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(
            invoke_llm_with_retry(
                call,
                user_id=user_id,
                thread_id=thread_id,
                label=label,
                max_attempts=max_attempts,
                timeout_seconds=timeout_seconds,
            )
        )
    finally:
        loop.close()


__all__ = [
    "is_transient_error",
    "invoke_llm_with_retry",
    "invoke_llm_with_retry_sync",
]