"""Assets de bronze: lista de actividades y descarga de FIT."""

from datetime import date

from dagster import (
    AssetExecutionContext,
    AssetKey,
    Backoff,
    MaterializeResult,
    MetadataValue,
    RetryPolicy,
    asset,
)

from etl_running.ingest.fit_download import download_pending
from etl_running.ingest.pipeline import run_ingest

from ..resources import DAILY_PARTITIONS

GARMIN_RETRY = RetryPolicy(max_retries=2, delay=30, backoff=Backoff.EXPONENTIAL)
MAX_RUNTIME_GARMIN = "3600"


def _day_for_run(context: AssetExecutionContext) -> tuple[date, str]:
    """Usa la partición si existe; el job diario no particionado usa hoy.

    El schedule y los backfills lanzan la partición explícita. `make run-daily` y
    `dagster job execute -j daily_pipeline` son no particionados y deben seguir
    funcionando de extremo a extremo; en ese caso se ingesta el día actual.
    """
    if context.has_partition_key:
        return date.fromisoformat(context.partition_key), context.partition_key
    today = date.today()
    start = context.resources.settings.start_date
    day = max(today, start)
    return day, day.isoformat()


@asset(
    key=AssetKey(["bronze", "activities"]),
    partitions_def=DAILY_PARTITIONS,
    group_name="bronze",
    description="Lista de actividades de Garmin; una partición diaria e inmutable.",
    retry_policy=GARMIN_RETRY,
    op_tags={"dagster/max_runtime": MAX_RUNTIME_GARMIN},
    required_resource_keys={"settings", "garmin_client"},
)
def bronze_activities(context: AssetExecutionContext) -> MaterializeResult:
    """Descarga una ventana de un día y escribe su partición, aunque esté vacía."""
    settings = context.resources.settings
    garmin_client = context.resources.garmin_client
    day, label = _day_for_run(context)
    context.log.info("Ingesta bronze para %s (partición %s)", day, label)
    summary = run_ingest(settings, garmin_client, day, day)
    return MaterializeResult(
        metadata={
            "run_id": summary.run_id,
            "day": label,
            "fetched": summary.fetched,
            "files_written": summary.files_written,
            "files_skipped": summary.files_skipped,
            "source": MetadataValue.text("Garmin Personal API"),
        }
    )


@asset(
    key=AssetKey(["bronze", "activity_fit"]),
    deps=[AssetKey(["silver", "activities"])],
    group_name="bronze",
    description="ZIP FIT originales de carreras elegibles; depende de Silver para el alcance.",
    retry_policy=GARMIN_RETRY,
    op_tags={"dagster/max_runtime": MAX_RUNTIME_GARMIN},
    required_resource_keys={"settings", "garmin_client"},
)
def bronze_activity_fit(context: AssetExecutionContext) -> MaterializeResult:
    """Descarga solo FIT pendientes mediante la misma función que usa la CLI."""
    settings = context.resources.settings
    garmin_client = context.resources.garmin_client
    counts = download_pending(settings, garmin_client)
    context.log.info("Resultado FIT: %s", dict(counts))
    metadata = {key: int(value) for key, value in counts.items()}
    metadata["total"] = sum(counts.values())
    return MaterializeResult(metadata=metadata)
