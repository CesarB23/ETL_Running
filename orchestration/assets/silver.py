"""Assets de Silver: actividades, plan, FIT y vínculos con workouts."""

from dagster import (
    AssetExecutionContext,
    AssetKey,
    AssetOut,
    Backoff,
    Config,
    MaterializeResult,
    RetryPolicy,
    asset,
    multi_asset,
)

from etl_running.silver.build import BuildResult, build_silver
from etl_running.silver.fit_build import build_fit
from etl_running.silver.plan_build import build_plan
from etl_running.silver.plan_links import collect_links

from ..resources import plan_uploads_path

LOCAL_RETRY = RetryPolicy(max_retries=1, delay=15, backoff=Backoff.EXPONENTIAL)
MAX_RUNTIME_LOCAL = "1800"


class SilverConfig(Config):
    """Permite forzar la reconstrucción desde la UI o por CLI."""

    full_refresh: bool = False


class LinksConfig(Config):
    """Fuerza a reconsultar la API de Garmin para los vínculos."""

    refresh: bool = False


def _silver_metadata(result: BuildResult) -> dict[str, object]:
    return {
        "built_at": result.built_at,
        "skipped": result.skipped,
        "wrote": result.wrote,
        "bronze_records": result.bronze_records,
        "bronze_unique": result.bronze_unique,
        "silver": result.silver,
        "quarantine": result.quarantine,
        "out_of_scope": result.out_of_scope_total,
        "warnings": result.warnings,
        "table_hash": result.table_hash,
        "reconciles": result.reconciles,
    }


@asset(
    key=AssetKey(["silver", "activities"]),
    deps=[AssetKey(["bronze", "activities"])],
    group_name="silver",
    description="Actividades running normalizadas, deduplicadas y reconciliadas con bronze.",
    retry_policy=LOCAL_RETRY,
    op_tags={"dagster/max_runtime": MAX_RUNTIME_LOCAL},
    required_resource_keys={"settings"},
)
def silver_activities(
    context: AssetExecutionContext,
    config: SilverConfig,
) -> MaterializeResult:
    """Llama a `build_silver`; la lógica y las validaciones viven en el ETL."""
    settings = context.resources.settings
    result = build_silver(settings, full_refresh=config.full_refresh)
    context.log.info(
        "Silver: %d carreras, %d en cuarentena, reconciliación=%s",
        result.silver,
        result.quarantine,
        result.reconciles,
    )
    return MaterializeResult(metadata=_silver_metadata(result))


@multi_asset(
    outs={
        "planned_workouts": AssetOut(
            key=AssetKey(["silver", "planned_workouts"]),
            description="Sesiones semanales del plan en Silver.",
        ),
        "planned_steps": AssetOut(
            key=AssetKey(["silver", "planned_steps"]),
            description="Pasos objetivos de cada sesión del plan.",
        ),
    },
    deps=[AssetKey(["bronze", "weekly_plan"])],
    group_name="silver",
    description="Plan semanal local (JSON de bronze) normalizado a dos tablas.",
    retry_policy=LOCAL_RETRY,
    op_tags={"dagster/max_runtime": MAX_RUNTIME_LOCAL},
    required_resource_keys={"settings"},
)
def silver_plan(context: AssetExecutionContext):
    """Una llamada a `build_plan` materializa las dos salidas."""
    settings = context.resources.settings
    result = build_plan(settings, plan_uploads_path())
    context.log.info(
        "Plan: %d semanas, %d sesiones, %d pasos, %d IDs Garmin",
        result["weeks"],
        result["sessions"],
        result["steps"],
        result["uploaded_ids"],
    )
    metadata = {
        "weeks": result["weeks"],
        "sessions": result["sessions"],
        "steps": result["steps"],
        "uploaded_ids": result["uploaded_ids"],
    }
    yield MaterializeResult(asset_key=AssetKey(["silver", "planned_workouts"]), metadata=metadata)
    yield MaterializeResult(asset_key=AssetKey(["silver", "planned_steps"]), metadata=metadata)


@multi_asset(
    outs={
        "activity_laps": AssetOut(
            key=AssetKey(["silver", "activity_laps"]),
            description="Laps y pasos de workout extraídos de los FIT.",
        ),
        "activity_records": AssetOut(
            key=AssetKey(["silver", "activity_records"]),
            description="Series temporales de los FIT (records).",
        ),
    },
    deps=[
        AssetKey(["silver", "activities"]),
        AssetKey(["bronze", "activity_fit"]),
    ],
    group_name="silver",
    description="Laps y records derivados de los ZIP FIT de bronze.",
    retry_policy=LOCAL_RETRY,
    op_tags={"dagster/max_runtime": MAX_RUNTIME_LOCAL},
    required_resource_keys={"settings"},
)
def silver_fit(context: AssetExecutionContext):
    """Una llamada a `build_fit` materializa laps y records."""
    settings = context.resources.settings
    result = build_fit(settings)
    context.log.info(
        "FIT: %d ZIP, %d laps, %d records, %d excepciones",
        result["fits"],
        result["laps"],
        result["records"],
        len(result["exceptions"]),
    )
    metadata = {
        "fits": result["fits"],
        "laps": result["laps"],
        "records": result["records"],
        "exceptions": len(result["exceptions"]),
    }
    yield MaterializeResult(asset_key=AssetKey(["silver", "activity_laps"]), metadata=metadata)
    yield MaterializeResult(asset_key=AssetKey(["silver", "activity_records"]), metadata=metadata)


@asset(
    key=AssetKey(["silver", "activity_workout_links"]),
    deps=[
        AssetKey(["silver", "activities"]),
        AssetKey(["silver", "planned_workouts"]),
    ],
    group_name="silver",
    description="Vínculos actividad ↔ workout por nombre exacto de la API (sin inventar IDs).",
    retry_policy=LOCAL_RETRY,
    op_tags={"dagster/max_runtime": MAX_RUNTIME_LOCAL},
    required_resource_keys={"settings", "garmin_client"},
)
def silver_activity_workout_links(
    context: AssetExecutionContext,
    config: LinksConfig,
) -> MaterializeResult:
    """Reutiliza `collect_links`, que solo asocia con evidencia de la API."""
    settings = context.resources.settings
    count = collect_links(settings, context.resources.garmin_client, refresh=config.refresh)
    context.log.info("Workouts enlazados: %d", count)
    return MaterializeResult(metadata={"links": count})
