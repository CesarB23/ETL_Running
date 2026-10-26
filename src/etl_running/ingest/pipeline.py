"""Orquestación de la ingesta de la lista de actividades hacia bronze."""

from __future__ import annotations

import json
import logging
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from etl_running.bronze.writer import BronzeWriter, new_run_id
from etl_running.common.config import Settings
from etl_running.ingest.cursor import CursorStore
from etl_running.ingest.extractors import extract_activities, local_date
from etl_running.ingest.garmin_client import ActivitySource

LOGGER = logging.getLogger("etl_running.ingest")

SOURCE = "garmin"
DATASET = "activities_list"
CURSOR_KEY = f"{SOURCE}/{DATASET}"
DEFAULT_LOOKBACK = 3


class WindowError(ValueError):
    """Ventana de fechas inválida."""


@dataclass(frozen=True)
class IngestSummary:
    run_id: str
    since: date
    until: date
    fetched: int
    days: int
    files_written: int
    files_skipped: int


def runs_log_path(lake_dir: Path) -> Path:
    return lake_dir / "_state" / "runs.jsonl"


def _log_run(lake_dir: Path, entry: dict[str, object]) -> None:
    path = runs_log_path(lake_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def resolve_window(
    settings: Settings,
    *,
    since: str | date | None,
    until: date | None,
    lookback: int,
    resume: bool,
    today: date,
) -> tuple[date, date]:
    """Calcula `[since, until]` validando que respete `START_DATE`.

    `since="last"` o `None` usa el cursor (menos `lookback - 1` días de solapamiento).
    Con `resume=True` (backfill) arranca desde el día del cursor sin lookback.
    """
    if lookback < 1:
        raise WindowError("--lookback debe ser >= 1")
    cursor = CursorStore(settings.lake_dir).get(CURSOR_KEY)
    if since is None or since == "last":
        if cursor is None:
            start = settings.start_date
        elif resume:
            start = cursor
        else:
            start = cursor - timedelta(days=lookback - 1)
        start = max(start, settings.start_date)
    else:
        start = since if isinstance(since, date) else date.fromisoformat(since)
    end = until or today
    settings.ensure_in_window(start)
    settings.ensure_in_window(end)
    if start > end:
        raise WindowError(f"El inicio {start} es posterior al fin {end}")
    return start, end


def run_ingest(
    settings: Settings,
    client: ActivitySource,
    since: date,
    until: date,
) -> IngestSummary:
    """Descarga `[since, until]` y escribe una partición por día (vacía si no hay datos)."""
    run_id = new_run_id()
    started = datetime.now(UTC).isoformat()
    t0 = time.monotonic()
    base = {"run_id": run_id, "dataset": CURSOR_KEY, "started_at": started}
    LOGGER.info("===== INICIO ingesta %s | run_id=%s =====", CURSOR_KEY, run_id)
    LOGGER.info("Ventana solicitada: %s → %s (%d días)", since, until, (until - since).days + 1)
    try:
        LOGGER.info("Paso 1/3 · Descargar la lista de actividades desde Garmin")
        activities = extract_activities(client, since, until)
        by_day: dict[date, list[dict]] = {}
        for activity in activities:
            by_day.setdefault(local_date(activity), []).append(activity)
        types = Counter((a.get("activityType") or {}).get("typeKey") or "?" for a in activities)
        LOGGER.info(
            "Descargadas %d actividades en %d días distintos. Por tipo: %s",
            len(activities),
            len(by_day),
            ", ".join(f"{k}={v}" for k, v in types.most_common()) or "ninguno",
        )

        LOGGER.info("Paso 2/3 · Escribir particiones en bronze (una por día, inmutables)")
        writer = BronzeWriter(settings.bronze_dir)
        cursor = CursorStore(settings.lake_dir)
        written = skipped = days = empty_written = 0
        previous = cursor.get(CURSOR_KEY)
        # El cursor solo avanza si la ventana es contigua con lo ya cargado; así una
        # carga parcial (p. ej. solo la última semana) no oculta días sin ingestar.
        contiguous = (
            since <= settings.start_date if previous is None else since <= previous + timedelta(1)
        )
        cursor_before = previous
        day = since
        while day <= until:
            todays = by_day.get(day, [])
            result = writer.write_partition(SOURCE, DATASET, day, todays, run_id)
            written += result.written
            skipped += not result.written
            empty_written += result.written and not todays
            days += 1
            level = logging.INFO if todays else logging.DEBUG
            if result.written:
                LOGGER.log(
                    level,
                    "dt=%s · %d actividades · ESCRITO %s (sha256 %s…)",
                    day,
                    len(todays),
                    result.path.name if result.path else "",
                    result.sha256[:8],
                )
            else:
                LOGGER.log(
                    level,
                    "dt=%s · %d actividades · SIN CAMBIOS (mismo hash que la versión anterior)",
                    day,
                    len(todays),
                )
            if contiguous and (previous is None or day > previous):
                cursor.set(CURSOR_KEY, day)
                previous = day
            day += timedelta(days=1)
        if empty_written:
            LOGGER.info("Días sin actividad registrados como partición vacía []: %d", empty_written)

        LOGGER.info("Paso 3/3 · Actualizar cursor")
        if previous != cursor_before:
            LOGGER.info("Cursor %s: %s → %s", CURSOR_KEY, cursor_before or "(vacío)", previous)
        elif contiguous:
            LOGGER.info("Cursor %s sin cambios (%s)", CURSOR_KEY, previous)
        else:
            LOGGER.warning(
                "Cursor %s NO avanza: la ventana %s → %s no enlaza con lo ya cargado "
                "(cursor=%s). Para cargar todo: backfill --from %s",
                CURSOR_KEY,
                since,
                until,
                cursor_before or "(vacío)",
                settings.start_date,
            )
    except BaseException as exc:
        _log_run(
            settings.lake_dir,
            {**base, "status": "error", "error": type(exc).__name__, "since": str(since)},
        )
        LOGGER.error(
            "===== FIN ingesta %s | run_id=%s | ERROR %s: %s | %.1f s =====",
            CURSOR_KEY,
            run_id,
            type(exc).__name__,
            exc,
            time.monotonic() - t0,
        )
        LOGGER.error("El cursor no avanzó más allá del último día escrito; puedes relanzar.")
        raise

    summary = IngestSummary(run_id, since, until, len(activities), days, written, skipped)
    _log_run(
        settings.lake_dir,
        {
            **base,
            "status": "ok",
            "since": str(since),
            "until": str(until),
            "fetched": summary.fetched,
            "files_written": written,
            "files_skipped": skipped,
        },
    )
    LOGGER.info(
        "===== FIN ingesta %s | run_id=%s | OK | %d actividades, %d archivos nuevos, "
        "%d sin cambios | %.1f s =====",
        CURSOR_KEY,
        run_id,
        summary.fetched,
        written,
        skipped,
        time.monotonic() - t0,
    )
    return summary
