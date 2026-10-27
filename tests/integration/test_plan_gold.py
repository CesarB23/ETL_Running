"""Match realista con plan y Silver sintéticos, aislados de la cuenta Garmin."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, date, datetime, time
from pathlib import Path

import duckdb
import polars as pl
from tests.unit.test_plan import sample_week

from etl_running.common.config import Settings
from etl_running.gold.plan_report import report_week
from etl_running.ingest.plan_loader import load_week
from etl_running.silver.fit_build import LAPS_SCHEMA, RECORDS_SCHEMA
from etl_running.silver.plan_build import build_plan
from etl_running.silver.plan_confirmations import confirm_match
from etl_running.silver.plan_links import collect_links
from etl_running.silver.schemas import ACTIVITIES_POLARS_SCHEMA, QUARANTINE_POLARS_SCHEMA

ROOT = Path(__file__).resolve().parents[2]


def _activity(activity_id: int, day: date):
    row = dict.fromkeys(ACTIVITIES_POLARS_SCHEMA)
    row.update(
        activity_id=activity_id,
        activity_type="running",
        is_manual=False,
        has_gps=False,
        start_utc=datetime.combine(day, time(8), UTC),
        start_local=datetime.combine(day, time(8)),
        local_date=day,
        tz_local="+00:00",
        utc_offset_min=0,
        distance_m=1000.0,
        duration_s=310.0,
        avg_speed_mps=1000 / 310,
        avg_hr=135.0,
        moderate_intensity_min=10,
        vigorous_intensity_min=0,
        bronze_run_id="synthetic",
        bronze_ingested_at=datetime(2026, 10, 26, tzinfo=UTC),
        source_path="synthetic.json",
    )
    return row


def test_plan_matching_workout_steps_fallback_and_missing(tmp_path):
    settings = Settings(lake_dir=tmp_path / "lake")
    silver = settings.silver_dir
    silver.mkdir(parents=True)
    week = sample_week()
    week_path = tmp_path / "week.json"
    week_path.write_text(json.dumps(week))
    assert load_week(settings, week_path)
    uploads = tmp_path / "uploads.json"
    uploads.write_text(
        json.dumps(
            {"workouts": {"2026-10-20": {"name": "Serie ficticia Garmin", "workoutId": 123}}}
        )
    )
    assert build_plan(settings, uploads)["sessions"] == 3

    activities = [
        _activity(1, date(2026, 10, 20)),
        _activity(2, date(2026, 10, 23)),
        _activity(3, date(2026, 10, 19)),
        _activity(4, date(2026, 10, 12)),
    ]
    pl.DataFrame(activities, schema=ACTIVITIES_POLARS_SCHEMA).write_parquet(
        silver / "activities.parquet"
    )

    class FakeClient:
        def get_activity_workouts(self, activity_id):
            return [{"workoutName": "Serie ficticia Garmin"}] if activity_id == 1 else []

    assert collect_links(settings, FakeClient()) == 1
    assert confirm_match(settings, date(2026, 10, 22), 2)
    laps = []
    for idx in (0, 1):
        lap = dict.fromkeys(LAPS_SCHEMA)
        lap.update(
            activity_id=1,
            lap_index=idx,
            wkt_step_index=2,
            distance_m=1000.0,
            duration_s=310.0,
            avg_speed_mps=1000 / 310,
            start_utc=datetime(2026, 10, 20, 8, 5 + idx * 6, tzinfo=UTC),
        )
        laps.append(lap)
    pl.DataFrame(laps, schema=LAPS_SCHEMA).write_parquet(silver / "activity_laps.parquet")
    records = []
    for idx, distance in enumerate((100.0, 900.0)):
        record = dict.fromkeys(RECORDS_SCHEMA)
        record.update(
            activity_id=2,
            ts_utc=datetime(2026, 10, 23, 8, idx, tzinfo=UTC),
            distance_m=distance,
            speed_mps=1000 / 310,
            timer_running=True,
        )
        records.append(record)
    pl.DataFrame(records, schema=RECORDS_SCHEMA).write_parquet(silver / "activity_records.parquet")
    (silver / "_quarantine").mkdir()
    pl.DataFrame(schema=QUARANTINE_POLARS_SCHEMA).write_parquet(
        silver / "_quarantine" / "activities.parquet"
    )
    env = {**os.environ, "LAKE_DIR": str(settings.lake_dir), "START_DATE": "2026-08-17"}
    dbt = str(Path(sys.prefix) / "bin" / "dbt")
    command = [dbt, "build", "--project-dir", "dbt", "--profiles-dir", "dbt"]
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]
    with duckdb.connect(str(settings.warehouse_path), read_only=True) as con:
        statuses = dict(
            con.execute("select status, count(*) from gold.fct_plan_sessions group by 1").fetchall()
        )
        assert statuses == {"done": 2, "missed": 1}
        matches = dict(
            con.execute(
                "select match_method, count(*) from gold.fct_plan_vs_actual group by 1"
            ).fetchall()
        )
        assert matches["wkt_step"] == 2 and matches["distance_segmentation"] == 1
        assert (
            con.execute(
                "select count(*) from gold.fct_plan_vs_actual where confidence = 'high'"
            ).fetchone()[0]
            == 2
        )
        assert (
            con.execute(
                "select plan_compliance_pct from gold.fct_weekly_summary "
                "where week_start = '2026-10-19'"
            ).fetchone()[0]
            == 75.0
        )
        extra = dict(
            con.execute(
                "select status, count(*) from gold.fct_unplanned_runs group by 1"
            ).fetchall()
        )
        assert extra == {"unplanned_extra": 1, "no_plan": 1}
    output = report_week(settings, date(2026, 10, 19))
    assert "75.0 %" in output and "no realizada" in output
    assert "desplazado +1 día · confirmación manual" in output
