"""Extractores: `(client, since, until) -> payload`."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from etl_running.ingest.garmin_client import ActivitySource

LOGGER = logging.getLogger("etl_running.ingest.extractors")

PAGE_SIZE = 50
MAX_PAGES = 200


def local_date(activity: dict[str, Any]) -> date:
    """Fecha local de inicio (`startTimeLocal`, formato `YYYY-MM-DD HH:MM:SS`)."""
    return date.fromisoformat(str(activity["startTimeLocal"])[:10])


def extract_activities(
    client: ActivitySource, since: date, until: date, *, page_size: int = PAGE_SIZE
) -> list[dict[str, Any]]:
    """Pagina `search_activities` de la más reciente hacia atrás hasta cruzar `since`.

    Descarta actividades fuera de `[since, until]` y deduplica por `activityId`.
    Conserva todos los tipos (D15: el filtro de running ocurre en silver).
    """
    LOGGER.info(
        "Paginando search_activities (más reciente → más antigua), ventana %s → %s, %d por página",
        since,
        until,
        page_size,
    )
    found: dict[Any, dict[str, Any]] = {}
    for page in range(MAX_PAGES):
        number = page + 1
        LOGGER.debug(
            "Página %d: solicitando start=%d limit=%d", number, page * page_size, page_size
        )
        batch = client.search_activities(start=page * page_size, limit=page_size)
        if not batch:
            LOGGER.info("Página %d: vacía. Fin de la paginación.", number)
            break
        oldest = min(local_date(a) for a in batch)
        in_window = 0
        for activity in batch:
            if since <= local_date(activity) <= until:
                in_window += 1
                found.setdefault(activity["activityId"], activity)
        LOGGER.info(
            "Página %d: %d recibidas, %d dentro de la ventana, más antigua: %s",
            number,
            len(batch),
            in_window,
            oldest,
        )
        if oldest < since:
            LOGGER.info(
                "Fin de la paginación: se cruzó %s (las anteriores se descartan, D10).", since
            )
            break
        if len(batch) < page_size:
            LOGGER.info("Fin de la paginación: última página (llegó incompleta).")
            break
    else:
        LOGGER.warning("Se alcanzó el máximo de %d páginas; puede haber datos sin leer", MAX_PAGES)
    result = sorted(found.values(), key=lambda a: (str(a["startTimeLocal"]), a["activityId"]))
    LOGGER.info("Actividades únicas dentro de la ventana: %d", len(result))
    return result
