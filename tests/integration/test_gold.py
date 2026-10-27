"""Gold/dbt contra lake sintético aislado: nunca toca el warehouse personal."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import duckdb
import polars as pl

from etl_running.silver.fit_build import LAPS_SCHEMA, RECORDS_SCHEMA
from etl_running.silver.plan_build import (
    CONFIRMATION_SCHEMA,
    LINK_SCHEMA,
    STEP_SCHEMA,
    WORKOUT_SCHEMA,
)
from etl_running.silver.schemas import ACTIVITIES_POLARS_SCHEMA, QUARANTINE_POLARS_SCHEMA

ROOT = Path(__file__).resolve().parents[2]
START = date(2026, 8, 17)


def test_dbt_gold_with_six_weeks_synthetic(tmp_path):
    lake = tmp_path / "lake"
    silver = lake / "silver"
    silver.mkdir(parents=True)
    rows = []
    # Seis lunes de carrera + una actividad sin minutos Garmin (NULL ≠ 0).
    for i, day_offset in enumerate([0, 3, 7, 14, 21, 28, 35], start=1):
        day = START + timedelta(days=day_offset)
        row = dict.fromkeys(ACTIVITIES_POLARS_SCHEMA)
        row.update(
            activity_id=i,
            activity_type="running",
            is_manual=False,
            has_gps=False,
            start_utc=datetime.combine(day, time(8), UTC),
            start_local=datetime.combine(day, time(8)),
            local_date=day,
            tz_local="+00:00",
            utc_offset_min=0,
            distance_m=1000.0,
            duration_s=600.0,
            avg_speed_mps=1000 / 600,
            avg_hr=120.0,
            moderate_intensity_min=None if day_offset == 3 else 10,
            vigorous_intensity_min=None if day_offset == 3 else 0,
            bronze_run_id="synthetic",
            bronze_ingested_at=datetime(2026, 10, 1, tzinfo=UTC),
            source_path="synthetic.json",
        )
        rows.append(row)
    pl.DataFrame(rows, schema=ACTIVITIES_POLARS_SCHEMA).write_parquet(silver / "activities.parquet")
    pl.DataFrame(schema=LAPS_SCHEMA).write_parquet(silver / "activity_laps.parquet")
    pl.DataFrame(schema=RECORDS_SCHEMA).write_parquet(silver / "activity_records.parquet")
    pl.DataFrame(schema=WORKOUT_SCHEMA).write_parquet(silver / "planned_workouts.parquet")
    pl.DataFrame(schema=STEP_SCHEMA).write_parquet(silver / "planned_steps.parquet")
    pl.DataFrame(schema=LINK_SCHEMA).write_parquet(silver / "activity_workout_links.parquet")
    pl.DataFrame(schema=CONFIRMATION_SCHEMA).write_parquet(silver / "plan_confirmations.parquet")
    (silver / "_quarantine").mkdir()
    pl.DataFrame(schema=QUARANTINE_POLARS_SCHEMA).write_parquet(
        silver / "_quarantine" / "activities.parquet"
    )

    env = {**os.environ, "LAKE_DIR": str(lake), "START_DATE": START.isoformat()}
    dbt = str(Path(sys.prefix) / "bin" / "dbt")
    commands = [dbt, "deps", "--project-dir", "dbt", "--profiles-dir", "dbt"]
    subprocess.run(commands, cwd=ROOT, env=env, check=True, capture_output=True, text=True)
    commands[1] = "build"

    def build():
        result = subprocess.run(commands, cwd=ROOT, env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]

    build()
    with duckdb.connect(str(lake / "warehouse.duckdb"), read_only=True) as con:
        assert con.execute("select count(*) from gold.fct_runs").fetchone()[0] == 7
        assert (
            con.execute(
                "select count(*) from gold.fct_weekly_summary where distance_km = 1"
            ).fetchone()[0]
            == 5
        )
        assert (
            con.execute(
                "select count(*) from gold.fct_weekly_summary where distance_km = 2"
            ).fetchone()[0]
            == 1
        )
        assert (
            con.execute(
                "select training_load from gold.fct_training_load where activity_date = ?",
                [START + timedelta(days=1)],
            ).fetchone()[0]
            == 0
        )
        assert (
            con.execute(
                "select training_load from gold.fct_training_load where activity_date = ?",
                [START + timedelta(days=3)],
            ).fetchone()[0]
            is None
        )
        early = con.execute(
            "select is_reliable, acwr from gold.fct_training_load where activity_date = ?",
            [START + timedelta(days=27)],
        ).fetchone()
        late = con.execute(
            "select is_reliable, acwr from gold.fct_training_load where activity_date = ?",
            [START + timedelta(days=31)],
        ).fetchone()
        assert early == (False, None)
        assert late[0] is True and abs(late[1] - 1.0) < 1e-9
        before = con.execute("select sum(distance_m) from gold.fct_weekly_summary").fetchone()
    build()
    with duckdb.connect(str(lake / "warehouse.duckdb"), read_only=True) as con:
        total = con.execute("select sum(distance_m) from gold.fct_weekly_summary").fetchone()
        assert total == before
