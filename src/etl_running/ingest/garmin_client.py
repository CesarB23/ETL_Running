"""Cliente de Garmin con autenticación, reintentos con backoff y límite de ritmo."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, Protocol

from etl_running.common.config import ConfigError, Settings

LOGGER = logging.getLogger("etl_running.ingest.client")

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class ActivitySource(Protocol):
    """Lo mínimo que el extractor necesita de un cliente."""

    def search_activities(self, *, start: int, limit: int) -> list[dict[str, Any]]: ...


class FitSource(ActivitySource, Protocol):
    def download_activity(self, activity_id: int) -> bytes: ...

    def get_activity_workouts(self, activity_id: int) -> Any: ...


class IngestError(RuntimeError):
    """Fallo no recuperable al hablar con Garmin."""


def _status_code(exc: BaseException) -> int | None:
    code = getattr(exc, "status_code", None)
    return code if isinstance(code, int) else None


def _is_network_error(exc: BaseException) -> bool:
    return isinstance(exc, ConnectionError | TimeoutError) or any(
        cls.__name__ in {"ConnectionError", "Timeout", "ReadTimeout", "ConnectTimeout"}
        for cls in type(exc).__mro__
    )


class ResilientClient:
    """Envuelve un cliente: 401 refresca el token una vez, 429/5xx reintentan con backoff.

    Política (ver `docs/ARCHITECTURE.md`):
    - 401: se llama a `refresh_token` una sola vez por llamada; si persiste, falla.
    - 429, 5xx y errores de red: hasta `max_retries` reintentos con espera exponencial
      (`base_delay * 2**intento`, tope `max_delay`) más jitter.
    - Cualquier otro error (400, 403, 404…): no se reintenta.
    - Ritmo: al menos `min_interval` segundos entre peticiones (concurrencia 1).
    """

    def __init__(
        self,
        inner: ActivitySource,
        *,
        refresh_token: Callable[[], None] | None = None,
        max_retries: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        min_interval: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._inner = inner
        self._refresh_token = refresh_token
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._min_interval = min_interval
        self._sleep = sleep
        self._clock = clock
        self._jitter = jitter
        self._last_request: float | None = None

    def search_activities(self, *, start: int, limit: int) -> list[dict[str, Any]]:
        LOGGER.debug("GET search_activities start=%d limit=%d", start, limit)
        result = self._call(lambda: self._inner.search_activities(start=start, limit=limit))
        if result is None:
            return []
        if not isinstance(result, list):
            raise IngestError(f"Respuesta inesperada de Garmin: {type(result).__name__}")
        return result

    def download_activity(self, activity_id: int) -> bytes:
        """Obtiene ZIP original, sin loguear el contenido ni credenciales."""
        result = self._call(lambda: self._inner.download_activity(activity_id))
        if not isinstance(result, bytes) or not result:
            raise IngestError("La descarga FIT no devolvió bytes")
        return result

    def get_activity_workouts(self, activity_id: int) -> Any:
        return self._call(lambda: self._inner.get_activity_workouts(activity_id))

    def _throttle(self) -> None:
        if self._last_request is not None:
            wait = self._min_interval - (self._clock() - self._last_request)
            if wait > 0:
                self._sleep(wait)
        self._last_request = self._clock()

    def _call(self, fn: Callable[[], Any]) -> Any:
        refreshed = False
        attempt = 0
        while True:
            self._throttle()
            try:
                result = fn()
            except Exception as exc:
                status = _status_code(exc)
                if status == 401 and not refreshed and self._refresh_token is not None:
                    refreshed = True
                    LOGGER.warning(
                        "Garmin rechazó el token (HTTP 401). Renovando el token y repitiendo "
                        "la petición (solo se intenta una vez)."
                    )
                    self._refresh_token()
                    continue
                retryable = status in RETRYABLE_STATUS or (
                    status is None and _is_network_error(exc)
                )
                if not retryable or attempt >= self._max_retries:
                    if retryable:
                        LOGGER.error(
                            "Se agotaron los %d reintentos (HTTP %s). Abortando.",
                            self._max_retries,
                            status,
                        )
                    else:
                        LOGGER.error(
                            "Error no recuperable (%s): no se reintenta.",
                            f"HTTP {status}" if status else type(exc).__name__,
                        )
                    raise
                delay = min(self._max_delay, self._base_delay * 2**attempt)
                delay += delay * 0.1 * self._jitter()
                attempt += 1
                LOGGER.warning(
                    "Error transitorio (%s). Reintento %d/%d en %.1f s.",
                    f"HTTP {status}" if status else type(exc).__name__,
                    attempt,
                    self._max_retries,
                    delay,
                )
                self._sleep(delay)
                continue
            return result


@contextmanager
def open_client(settings: Settings) -> Iterator[ResilientClient]:
    """Abre un cliente real de la Personal API con refresco de token."""
    from garmin_personal_api import GarminPersonalApiClient, PersonalApiAuthenticator

    if not settings.api_key:
        raise ConfigError(
            "Falta GARMIN_PERSONAL_API_KEY (créala en "
            "https://connect.garmin.com/app/settings/personalApiToken y ponla en .env)"
        )
    api_key = settings.api_key
    LOGGER.info("Autenticando con la Garmin Personal API (token en caché o nuevo)")
    with PersonalApiAuthenticator() as authenticator:
        token = authenticator.obtain_token(api_key)
        LOGGER.info("Autenticación correcta; cliente listo")
        with GarminPersonalApiClient(token.access_token) as raw:

            def refresh() -> None:
                LOGGER.info("Solicitando un token nuevo a Garmin")
                raw.update_bearer_token(
                    authenticator.obtain_token(api_key, force_refresh=True).access_token
                )

            yield ResilientClient(raw, refresh_token=refresh)  # type: ignore[arg-type]
