"""Asset checks de frescura, volumen y reconciliación bronze↔silver."""

import json
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from dagster import AssetCheckResult, AssetCheckSeverity, asset_check

from etl_running.ingest.pipeline import runs_log_path
from etl_running.silver.build import activities_path, load_summary

from .assets.silver import silver_activities

FRESHNESS_MAX_HOURS = 36.0


def last_successful_ingest(lake_dir: Path) -> datetime | None:
    """Última entrada `status=ok` de `_state/runs.jsonl`, en UTC."""
    path = runs_log_path(lake_dir)
    if not path.is_file():
        return None
    latest: datetime | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("status") != "ok":
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


@asset_check(
    asset=silver_activities,
    name="freshness_36h",
    description="Avisa si la última ingesta correcta tiene más de 36 horas.",
    blocking=False,
    required_resource_keys={"settings"},
)
def freshness_check(context) -> AssetCheckResult:
    settings = context.resources.settings
    latest = last_successful_ingest(settings.lake_dir)
    if latest is None:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.WARN,
            metadata={"detail": "sin ninguna ingesta correcta registrada"},
        )
    age_hours = (datetime.now(UTC) - latest).total_seconds() / 3600.0
    return AssetCheckResult(
        passed=age_hours <= FRESHNESS_MAX_HOURS,
        severity=AssetCheckSeverity.WARN,
        metadata={
            "last_successful_ingest": latest.isoformat(),
            "age_hours": round(age_hours, 2),
            "threshold_hours": FRESHNESS_MAX_HOURS,
        },
    )


@asset_check(
    asset=silver_activities,
    name="volume_positive",
    description="Silver debe contener al menos una actividad running.",
    blocking=False,
    required_resource_keys={"settings"},
)
def volume_check(context) -> AssetCheckResult:
    settings = context.resources.settings
    path = activities_path(settings.silver_dir)
    if not path.is_file():
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            metadata={"detail": "falta silver/activities.parquet"},
        )
    count = pl.read_parquet(path).height
    return AssetCheckResult(
        passed=count > 0,
        severity=AssetCheckSeverity.ERROR,
        metadata={"activities": count},
    )


@asset_check(
    asset=silver_activities,
    name="bronze_silver_reconciles",
    description="bronze único = silver + cuarentena + fuera de alcance.",
    blocking=False,
    required_resource_keys={"settings"},
)
def reconciliation_check(context) -> AssetCheckResult:
    settings = context.resources.settings
    summary = load_summary(settings.silver_dir)
    if summary is None:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            metadata={"detail": "falta _build.json de Silver"},
        )
    return AssetCheckResult(
        passed=summary.reconciles,
        severity=AssetCheckSeverity.ERROR,
        metadata={
            "bronze_unique": summary.bronze_unique,
            "silver": summary.silver,
            "quarantine": summary.quarantine,
            "out_of_scope": summary.out_of_scope_total,
        },
    )


# Se exporta como lista para que `definitions.py` no dependa del nombre interno
# que Dagster asigna a cada AssetChecksDefinition.
SILVER_CHECKS = [
    freshness_check,
    volume_check,
    reconciliation_check,
]
