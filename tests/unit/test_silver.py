"""Silver con datos sintéticos únicamente; nunca usa el lake real ni la red."""

from __future__ import annotations

import copy
import json
from dataclasses import asdict
from datetime import date

import duckdb
import polars as pl
import pyarrow.parquet as pq
import pytest

from etl_running.bronze.writer import BronzeWriter
from etl_running.common.config import Settings
from etl_running.silver.build import (
    activities_path,
    build_silver,
    load_summary,
    quarantine_path,
    summary_path,
)
from etl_running.silver.parsers.activities import ParseError, parse_activity
from etl_running.silver.report import format_silver_report


@pytest.fixture
def settings(tmp_path):
    return Settings(lake_dir=tmp_path / "lake")


def write_activities(settings, activities, run_id="run1"):
    writer = BronzeWriter(settings.bronze_dir)
    for day, payload in activities.items():
        writer.write_partition(
            "garmin", "activities_list", date.fromisoformat(day), payload, run_id
        )


def one(activities_fixture, activity_id=101, day="2026-10-20", **updates):
    row = copy.deepcopy(activities_fixture[0])
    row.update({"activityId": activity_id, "startTimeLocal": f"{day} 07:30:00"})
    row.update(updates)
    return row


def test_build_reconciles_fixture_and_duckdb_query(settings, activities_fixture):
    payload = activities_fixture
    write_activities(settings, {a["startTimeLocal"][:10]: [a] for a in payload})
    result = build_silver(settings, full_refresh=True)
    assert (result.bronze_unique, result.silver, result.quarantine, result.out_of_scope_total) == (
        5,
        3,
        0,
        2,
    )
    assert result.reconciles
    df = pl.read_parquet(activities_path(settings.silver_dir))
    assert df["activity_id"].n_unique() == 3
    assert set(df["activity_type"]) == {"running"}
    assert df.filter(pl.col("avg_hr").is_null()).height >= 1
    sql = "select count(*), count(distinct activity_id) from read_parquet(?)"
    assert duckdb.execute(sql, [str(activities_path(settings.silver_dir))]).fetchone() == (3, 3)
    weekly = duckdb.execute(
        "select date_trunc('week', start_utc), count(*) from read_parquet(?) group by 1",
        [str(activities_path(settings.silver_dir))],
    ).fetchall()
    assert sum(row[1] for row in weekly) == 3
    assert pl.read_parquet(quarantine_path(settings.silver_dir)).height == 0
    metadata = pq.read_metadata(activities_path(settings.silver_dir))
    assert {
        metadata.row_group(i).column(j).compression
        for i in range(metadata.num_row_groups)
        for j in range(metadata.num_columns)
    } == {"UNCOMPRESSED"}
    report = format_silver_report(settings.silver_dir, settings.running_type_keys)
    assert "Cuadra: sí" in report and "cycling" in report and "other" in report


def test_second_run_no_changes_and_full_refresh_equivalent(settings, activities_fixture):
    write_activities(settings, {a["startTimeLocal"][:10]: [a] for a in activities_fixture})
    first = build_silver(settings)
    before = activities_path(settings.silver_dir).read_bytes()
    summary_before = summary_path(settings.silver_dir).read_bytes()
    second = build_silver(settings)
    assert second.skipped and not second.wrote
    assert activities_path(settings.silver_dir).read_bytes() == before
    assert summary_path(settings.silver_dir).read_bytes() == summary_before
    refreshed = build_silver(settings, full_refresh=True)
    assert refreshed.table_hash == first.table_hash
    assert pl.read_parquet(activities_path(settings.silver_dir)).height == first.silver


def test_old_compression_is_migrated_without_changing_logical_data(settings, activities_fixture):
    write_activities(settings, {a["startTimeLocal"][:10]: [a] for a in activities_fixture})
    first = build_silver(settings)
    path = activities_path(settings.silver_dir)
    pl.read_parquet(path).write_parquet(path, compression="zstd")
    previous = load_summary(settings.silver_dir)
    assert previous is not None
    previous.fingerprint = "fingerprint-anterior-al-cambio-de-codec"
    summary_path(settings.silver_dir).write_text(json.dumps(asdict(previous)))

    updated = build_silver(settings)
    assert updated.wrote and updated.table_hash == first.table_hash
    assert pq.read_metadata(path).row_group(0).column(0).compression == "UNCOMPRESSED"


def test_latest_day_version_and_latest_activity_win(settings, activities_fixture):
    a = one(activities_fixture, distance=1000.0)
    old = one(activities_fixture, 102, distance=2000.0)
    same_id_other_day = one(activities_fixture, 101, day="2026-10-19", distance=3000.0)
    write_activities(settings, {"2026-10-19": [same_id_other_day], "2026-10-20": [a, old]})
    first = build_silver(settings)
    # Más tarde Garmin corrige el mismo día. La partición antigua desaparece de la vista,
    # y activity_id=101 más reciente reemplaza al de otro día.
    writer = BronzeWriter(settings.bronze_dir)
    writer.write_partition(
        "garmin",
        "activities_list",
        date(2026, 10, 20),
        [one(activities_fixture, 101, distance=1500.0)],
        "run2",
    )
    second = build_silver(settings)
    df = pl.read_parquet(activities_path(settings.silver_dir))
    assert first.silver == 2 and second.silver == 1
    assert second.duplicates_dropped == 1
    assert df["distance_m"].item() == 1500
    assert second.reconciles


def test_invalid_row_quarantined_with_source_and_reason(settings, activities_fixture):
    good = one(activities_fixture, 10)
    invalid_distance = one(activities_fixture, 11, distance=-1)
    missing_duration = one(activities_fixture, 12, duration=None)
    malformed_date = one(activities_fixture, 13, startTimeGMT="invalid")
    unknown_type = one(activities_fixture, 14, activityType={})
    write_activities(
        settings,
        {"2026-10-20": [good, invalid_distance, missing_duration, malformed_date, unknown_type]},
    )
    result = build_silver(settings)
    assert (result.silver, result.quarantine, result.out_of_scope_total) == (1, 4, 0)
    q = pl.read_parquet(quarantine_path(settings.silver_dir))
    assert all(q["source_path"].str.contains("dt=2026-10-20"))
    assert "distance_m" in " ".join(q["reason"])
    assert "duration_s" in " ".join(q["reason"])
    assert result.reconciles


def test_manual_no_hr_treadmill_and_dst(settings, activities_fixture):
    manual = one(
        activities_fixture,
        10,
        manualActivity=True,
        averageHR=None,
        maxHR=None,
        startLatitude=None,
        startLongitude=None,
        moderateIntensityMinutes=None,
    )
    treadmill = one(
        activities_fixture, 11, day="2026-10-25", activityType={"typeKey": "treadmill_running"}
    )
    treadmill["startTimeGMT"] = "2026-10-25 06:30:00"  # +01:00
    dst = one(activities_fixture, 12, day="2026-10-26")
    dst["startTimeGMT"] = "2026-10-26 05:30:00"  # +02:00
    write_activities(
        settings, {"2026-10-20": [manual], "2026-10-25": [treadmill], "2026-10-26": [dst]}
    )
    assert build_silver(settings).silver == 3
    df = pl.read_parquet(activities_path(settings.silver_dir))
    m = df.filter(pl.col("activity_id") == 10).row(0, named=True)
    assert m["is_manual"] and not m["has_gps"]
    assert m["avg_hr"] is None and m["moderate_intensity_min"] is None
    assert not df.filter(pl.col("activity_id") == 11)["has_gps"].item()
    assert df.filter(pl.col("activity_id") == 11)["utc_offset_min"].item() == 60
    assert df.filter(pl.col("activity_id") == 12)["utc_offset_min"].item() == 120


def test_out_of_range_hr_becomes_null_with_warning(settings, activities_fixture):
    a = one(activities_fixture, averageHR=300)
    write_activities(settings, {"2026-10-20": [a]})
    result = build_silver(settings)
    assert result.silver == 1 and result.warnings == 1
    assert pl.read_parquet(activities_path(settings.silver_dir))["avg_hr"].item() is None


def test_missing_bronze_produces_empty_tables_and_report(settings):
    assert "no construido" in format_silver_report(settings.silver_dir, settings.running_type_keys)
    result = build_silver(settings)
    assert result.reconciles and result.silver == 0
    assert pl.read_parquet(activities_path(settings.silver_dir)).height == 0


def test_bad_numeric_rejected_without_leaking_value(activities_fixture):
    a = one(activities_fixture, distance="PRIVATE_NAME")
    with pytest.raises(ParseError, match="distance no es numérico") as exc:
        parse_activity(a)
    assert "PRIVATE_NAME" not in str(exc.value)


def test_cli_build_and_report_with_synthetic_bronze(
    settings, activities_fixture, monkeypatch, capsys
):
    from etl_running.cli import main

    write_activities(settings, {a["startTimeLocal"][:10]: [a] for a in activities_fixture})
    monkeypatch.setenv("LAKE_DIR", str(settings.lake_dir))
    assert main(["silver", "build", "--full-refresh"]) == 0
    assert "silver:        3" in capsys.readouterr().out
    assert main(["silver", "build"]) == 0
    assert "sin cambios" in capsys.readouterr().out
    assert main(["silver", "report"]) == 0
    assert "Cuadra: sí" in capsys.readouterr().out


def test_empty_scope_and_quarantine_rebuild(settings, activities_fixture):
    invalid = one(activities_fixture, 15, distance=-2)
    write_activities(settings, {"2026-10-20": [invalid]})
    first = build_silver(settings)
    assert (first.silver, first.quarantine) == (0, 1)
    quarantine_path(settings.silver_dir).unlink()
    second = build_silver(settings)
    assert not second.skipped and quarantine_path(settings.silver_dir).is_file()
