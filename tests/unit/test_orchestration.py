"""Orquestación Dagster con datos sintéticos: definiciones, assets y checks."""

from __future__ import annotations

import json
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import polars as pl
import pytest
from dagster import (
    AssetKey,
    AssetSelection,
    DagsterEventType,
    DagsterInstance,
    Definitions,
    ResourceDefinition,
    RetryPolicy,
    asset,
    build_run_status_sensor_context,
    build_schedule_context,
    build_sensor_context,
    define_asset_job,
    materialize,
)
from tests.unit.fakes import FakeClient
from tests.unit.fit_fixture import synthetic_zip

from etl_running.bronze.writer import BronzeWriter
from etl_running.common.config import Settings

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def dbt_manifest() -> Path:
    """Genera el manifest si el checkout está limpio (CI no versiona target/)."""
    path = ROOT / "dbt" / "target" / "manifest.json"
    if not path.is_file():
        subprocess.run(
            ["dbt", "deps", "--project-dir", "dbt", "--profiles-dir", "dbt"],
            cwd=ROOT,
            check=True,
        )
        subprocess.run(
            ["dbt", "parse", "--project-dir", "dbt", "--profiles-dir", "dbt"],
            cwd=ROOT,
            check=True,
        )
    return path


class FakePipelineClient(FakeClient):
    """Cliente de Garmin falso con lista, FIT y workouts (todo sintético)."""

    def download_activity(self, activity_id: int) -> bytes:
        return synthetic_zip()

    def get_activity_workouts(self, activity_id: int):
        return []


@pytest.fixture
def orchestration_lake(tmp_path, activities_fixture, monkeypatch):
    lake = tmp_path / "lake"
    settings = Settings(lake_dir=lake, start_date=date(2026, 8, 17))
    client = FakePipelineClient(activities_fixture)
    uploads = tmp_path / "uploads.json"
    monkeypatch.setenv("GARMIN_UPLOADS_JSON", str(uploads))
    resources = {
        "settings": ResourceDefinition.hardcoded_resource(settings),
        "garmin_client": ResourceDefinition.hardcoded_resource(client),
    }
    return lake, settings, resources


def _materialize(assets, resources, **kwargs):
    return materialize(assets, resources=resources, raise_on_error=True, **kwargs)


def test_definitions_have_full_graph_schedule_sensor_and_checks(dbt_manifest):
    from orchestration.definitions import defs

    keys = set(defs.resolve_all_asset_keys())
    assert AssetKey(["bronze", "activities"]) in keys
    assert AssetKey(["silver", "activities"]) in keys
    assert AssetKey(["silver", "activity_laps"]) in keys
    assert AssetKey(["gold", "alerts"]) in keys
    assert AssetKey(["fct_runs"]) in keys

    graph = defs.resolve_asset_graph()
    assert AssetKey(["silver", "activities"]) in graph.get(AssetKey(["stg_activities"])).parent_keys
    assert AssetKey(["stg_activities"]) in graph.get(AssetKey(["fct_runs"])).parent_keys

    job = defs.resolve_job_def("daily_pipeline")
    assert job.partitions_def is not None
    schedule = defs.get_schedule_def("daily_pipeline_schedule")
    assert schedule.execution_timezone == "America/Mexico_City"
    assert schedule.cron_schedule == "0 20 * * *"
    scheduled_at = datetime(2026, 10, 28, 20, 0, tzinfo=ZoneInfo("America/Mexico_City"))
    with build_schedule_context(scheduled_execution_time=scheduled_at) as context:
        tick = schedule.evaluate_tick(context)
    assert [request.partition_key for request in tick.run_requests] == ["2026-10-28"]
    assert {"new_activity_sensor", "pipeline_failure_log"} <= {
        sensor.name for sensor in defs.sensors
    }
    check_names = {spec.name for definition in defs.asset_checks for spec in definition.check_specs}
    assert {"freshness_36h", "volume_positive", "bronze_silver_reconciles"} <= check_names


def test_bronze_silver_fit_and_checks_with_fake_client(orchestration_lake):
    from orchestration.assets.bronze import bronze_activities, bronze_activity_fit
    from orchestration.assets.silver import silver_activities, silver_fit, silver_plan
    from orchestration.checks import SILVER_CHECKS

    lake, settings, resources = orchestration_lake
    _materialize([bronze_activities], resources, partition_key="2026-10-20")

    # Segunda ingesta del mismo día: bronze es idempotente (no añade otra versión).
    _materialize([bronze_activities], resources, partition_key="2026-10-20")
    manifest = BronzeWriter(settings.bronze_dir).read_manifest().to_pylist()
    assert len(manifest) == 1

    result = _materialize([silver_activities, *SILVER_CHECKS], resources)
    assert result.success
    activities = pl.read_parquet(lake / "silver" / "activities.parquet")
    assert activities.height == 1
    evaluations = {item.check_name: item for item in result.get_asset_check_evaluations()}
    assert evaluations["freshness_36h"].passed
    assert evaluations["volume_positive"].passed
    assert evaluations["bronze_silver_reconciles"].passed

    _materialize([bronze_activity_fit], resources)
    _materialize([silver_fit], resources)
    assert pl.read_parquet(lake / "silver" / "activity_laps.parquet").height == 2
    assert pl.read_parquet(lake / "silver" / "activity_records.parquet").height == 2

    _materialize([silver_plan], resources)
    assert (lake / "silver" / "planned_workouts.parquet").is_file()
    assert (lake / "silver" / "planned_steps.parquet").is_file()


def test_full_daily_job_builds_gold_from_empty_temporary_lake(
    tmp_path, activities_fixture, monkeypatch
):
    """Punto 1: pipeline completo de Dagster desde cero, sin tocar el lake real."""
    from orchestration.definitions import defs
    from orchestration.resources import DBT_RESOURCE

    # Dagster no expone la partición del día en curso hasta que cierre su ventana.
    run_day = date.today() - timedelta(days=1)
    activities = []
    for activity in activities_fixture:
        item = dict(activity)
        item["startTimeLocal"] = f"{run_day.isoformat()} 07:30:00"
        item["startTimeGMT"] = f"{run_day.isoformat()} 13:30:00"
        activities.append(item)

    lake = tmp_path / "lake-vacio"
    assert not lake.exists()
    settings = Settings(lake_dir=lake, start_date=date(2026, 8, 17))
    client = FakePipelineClient(activities)
    monkeypatch.setenv("GARMIN_UPLOADS_JSON", str(tmp_path / "uploads.json"))
    monkeypatch.setenv("LAKE_DIR", str(lake))

    job = defs.resolve_job_def("daily_pipeline")
    result = job.execute_in_process(
        partition_key=run_day.isoformat(),
        resources={
            "settings": settings,
            "garmin_client": client,
            "dbt": DBT_RESOURCE,
        },
        raise_on_error=True,
    )

    assert result.success
    assert (lake / "bronze" / "_manifest.parquet").is_file()
    assert (lake / "silver" / "activities.parquet").is_file()
    assert (lake / "silver" / "activity_laps.parquet").is_file()
    assert (lake / "warehouse.duckdb").is_file()
    with duckdb.connect(str(lake / "warehouse.duckdb"), read_only=True) as con:
        assert con.execute("select count(*) from gold.fct_runs").fetchone()[0] > 0
        assert con.execute("select count(*) from gold.fct_run_laps").fetchone()[0] > 0


def test_freshness_helper_reports_last_success(tmp_path):
    from orchestration.checks import last_successful_ingest

    log = tmp_path / "_state" / "runs.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "status": "ok",
                        "started_at": "2026-10-20T06:00:00+00:00",
                        "fetched": 1,
                    }
                ),
                json.dumps({"status": "error", "started_at": "2026-10-21T06:00:00+00:00"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert last_successful_ingest(tmp_path).isoformat() == "2026-10-20T06:00:00+00:00"


def test_sensor_partition_respects_start_date():
    from orchestration.sensors import sensor_partition_for

    settings = Settings(start_date=date(2026, 8, 17))
    assert sensor_partition_for(date(2026, 1, 1), settings) == "2026-08-17"
    assert sensor_partition_for(date(2026, 10, 20), settings) == "2026-10-20"


def test_new_activity_sensor_requests_run_for_pending_fit(
    tmp_path, activities_fixture, monkeypatch
):
    """El sensor positivo lanza el job cuando Silver tiene un FIT pendiente."""
    from orchestration.assets.bronze import bronze_activities
    from orchestration.assets.silver import silver_activities
    from orchestration.definitions import defs
    from orchestration.sensors import new_activity_sensor

    run_day = date.today() - timedelta(days=1)
    activities = []
    for activity in activities_fixture:
        item = dict(activity)
        item["startTimeLocal"] = f"{run_day.isoformat()} 07:30:00"
        item["startTimeGMT"] = f"{run_day.isoformat()} 13:30:00"
        activities.append(item)

    lake = tmp_path / "sensor-lake"
    settings = Settings(lake_dir=lake, start_date=date(2026, 8, 17))
    client = FakePipelineClient(activities)
    monkeypatch.setenv("LAKE_DIR", str(lake))
    monkeypatch.setenv("START_DATE", settings.start_date.isoformat())
    monkeypatch.setenv("GARMIN_UPLOADS_JSON", str(tmp_path / "uploads.json"))
    resources = {
        "settings": ResourceDefinition.hardcoded_resource(settings),
        "garmin_client": ResourceDefinition.hardcoded_resource(client),
    }
    _materialize([bronze_activities], resources, partition_key=run_day.isoformat())
    _materialize([silver_activities], resources)

    context = build_sensor_context(definitions=defs, sensor_name="new_activity_sensor")
    result = new_activity_sensor.evaluate_tick(context)

    assert len(result.run_requests) == 1
    request = result.run_requests[0]
    assert request.run_key.startswith("new-activity-")
    assert request.tags["trigger"] == "new_activity"
    today_mexico = datetime.now(ZoneInfo("America/Mexico_City")).date().isoformat()
    assert request.partition_key == today_mexico


def test_pipeline_failure_retries_and_sensor_logs_failure(tmp_path, monkeypatch):
    """Fallo 503 sintético: reintentos Dagster y log de fallo en lake temporal."""
    from orchestration.assets.bronze import bronze_activities
    from orchestration.definitions import defs
    from orchestration.sensors import pipeline_failure_log

    assert bronze_activities.op.retry_policy.max_retries == 2
    attempts = {"count": 0}

    @asset(retry_policy=RetryPolicy(max_retries=2, delay=0))
    def fail_three_times():
        attempts["count"] += 1
        raise RuntimeError("fallo controlado HTTP 503 de Garmin")

    failing_job = Definitions(
        assets=[fail_three_times],
        jobs=[
            define_asset_job(
                name="daily_pipeline",
                selection=AssetSelection.assets(fail_three_times),
            )
        ],
    ).resolve_job_def("daily_pipeline")

    lake = tmp_path / "failure-lake"
    monkeypatch.setenv("LAKE_DIR", str(lake))
    monkeypatch.setenv("START_DATE", "2026-08-17")

    with DagsterInstance.ephemeral() as instance:
        result = failing_job.execute_in_process(
            instance=instance,
            raise_on_error=False,
        )
        failed_run = instance.get_run_by_id(result.run_id)
        failure_events = result.get_step_failure_events()
        retry_count = sum(
            event.event_type_value == DagsterEventType.STEP_UP_FOR_RETRY.value
            for event in result.all_events
        )
        assert failed_run is not None
        assert len(failure_events) == 1
        assert failed_run.status.value == "FAILURE"
        assert attempts["count"] == 3
        assert retry_count == 2

        context = build_run_status_sensor_context(
            sensor_name="pipeline_failure_log",
            dagster_event=failure_events[0],
            dagster_instance=instance,
            dagster_run=failed_run,
            repository_def=defs.get_repository_def(),
        )
        pipeline_failure_log._run_status_sensor_fn(context)

    failure_log = lake / "_state" / "orchestration_failures.log"
    contents = failure_log.read_text(encoding="utf-8")
    assert failed_run.run_id in contents
    assert "fallo controlado HTTP 503 de Garmin" in contents
