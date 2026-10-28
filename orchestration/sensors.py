"""Sensores: nuevas actividades y registro local de fallos."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dagster import (
    DefaultSensorStatus,
    RunFailureSensorContext,
    RunRequest,
    SkipReason,
    run_failure_sensor,
    sensor,
)

from etl_running.common.config import Settings
from etl_running.ingest.fit_download import pending_fits
from etl_running.ingest.pipeline import runs_log_path
from etl_running.silver.build import activities_path

from .jobs import daily_pipeline
from .resources import TIMEZONE


def _latest_ingest_with_data(lake_dir: Path) -> datetime | None:
    """Última ingesta correcta que trajo al menos una actividad."""
    path = runs_log_path(lake_dir)
    if not path.is_file():
        return None
    latest: datetime | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("status") != "ok" or int(entry.get("fetched") or 0) <= 0:
            continue
        raw = entry.get("started_at")
        if not isinstance(raw, str):
            continue
        try:
            ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        if latest is None or ts > latest:
            latest = ts
    return latest


def _silver_mtime(settings: Settings) -> datetime | None:
    path = activities_path(settings.silver_dir)
    if not path.is_file():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def _definitely_pending(settings: Settings) -> tuple[list[int], str]:
    """Devuelve IDs con FIT pendiente o un motivo para no lanzar el sensor."""
    try:
        pending, excluded = pending_fits(settings)
    except FileNotFoundError:
        return [], "Silver aún no existe"
    if pending:
        return [int(row["activity_id"]) for row in pending], "FIT pendiente"

    # Ventana de carrera: bronze ya trajo una actividad nueva pero Silver todavía
    # no se ha reconstruido. Evita depender solo de que sea elegible para FIT.
    bronze_at = _latest_ingest_with_data(settings.lake_dir)
    silver_at = _silver_mtime(settings)
    if bronze_at is not None and (silver_at is None or bronze_at > silver_at):
        return [], "bronze más reciente que Silver"
    return [], f"sin novedades (excluidas: {dict(excluded)})"


@sensor(
    job=daily_pipeline,
    name="new_activity_sensor",
    description=(
        "Cada 15 min busca FIT pendientes o bronze más nuevo que Silver y lanza "
        "el pipeline particionado. No descarga nada por sí mismo."
    ),
    minimum_interval_seconds=900,
    default_status=DefaultSensorStatus.RUNNING,
)
def new_activity_sensor(context):
    settings = Settings.from_env()
    pending_ids, reason = _definitely_pending(settings)
    if not pending_ids and reason != "bronze más reciente que Silver":
        yield SkipReason(reason)
        return

    today = datetime.now(ZoneInfo(TIMEZONE)).date()
    partition = max(today, settings.start_date).isoformat()
    digest = hashlib.sha256(
        (",".join(str(value) for value in sorted(pending_ids)) + reason).encode()
    ).hexdigest()[:12]
    context.log.info("Sensor: %s; partición %s", reason, partition)
    yield RunRequest(
        partition_key=partition,
        run_key=f"new-activity-{partition}-{digest}",
        tags={"trigger": "new_activity", "reason": reason},
    )


@run_failure_sensor(
    name="pipeline_failure_log",
    description="Registra fallos de Dagster en lake/_state/orchestration_failures.log.",
    monitored_jobs=[daily_pipeline],
    default_status=DefaultSensorStatus.RUNNING,
)
def pipeline_failure_log(context: RunFailureSensorContext) -> None:
    """No envía datos fuera del Mac; solo deja una línea legible para diagnóstico."""
    settings = Settings.from_env()
    path = settings.lake_dir / "_state" / "orchestration_failures.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    failure_event = context.failure_event
    failure_data = getattr(failure_event, "event_specific_data", None)
    error = getattr(failure_data, "error", None)
    root_error = getattr(error, "cause", None) or getattr(error, "context", None) or error
    message = getattr(root_error, "message", None) or getattr(error, "message", None)
    message = message or getattr(failure_event, "message", None)
    message = (str(message).splitlines()[0] if message else "sin detalle")[:500]
    run = context.dagster_run
    line = (
        f"{datetime.now(UTC).isoformat()} | job={run.job_name} | run_id={run.run_id} | "
        f"partition={getattr(run, 'partition_key', None) or '-'} | {message}\n"
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
    context.log.error("Fallo registrado en %s", path)


def sensor_partition_for(day: date, settings: Settings) -> str:
    """Utilidad pequeña para tests y documentación."""
    return max(day, settings.start_date).isoformat()
