"""FIT sintético (no datos de Garmin reales ni red)."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from tests.unit.fit_fixture import synthetic_fit, synthetic_zip

from etl_running.bronze.fit import FitArchiveError, FitWriter, fit_bytes
from etl_running.bronze.writer import BronzeWriter
from etl_running.common.config import Settings
from etl_running.ingest.fit_download import download_pending, pending_fits
from etl_running.silver.build import build_silver
from etl_running.silver.fit_build import build_fit
from etl_running.silver.parsers.fit import FitParseError, parse_fit
from etl_running.tools.show_run import render_run


@pytest.fixture
def settings(tmp_path, activities_fixture):
    settings = Settings(lake_dir=tmp_path / "lake")
    a = activities_fixture[0].copy()
    a["distance"] = 1000.0
    BronzeWriter(settings.bronze_dir).write_partition(
        "garmin", "activities_list", date(2026, 10, 20), [a], "test"
    )
    build_silver(settings)
    return settings


def test_parser_laps_records_steps_gps_and_corrupt():
    parsed = parse_fit(synthetic_fit(), 10)
    assert [lap["wkt_step_index"] for lap in parsed.laps] == [0, 1]
    assert [lap["distance_m"] for lap in parsed.laps] == [500, 500]
    assert len(parsed.records) == 2  # timestamp duplicado => última observación
    assert parsed.records[-1]["heart_rate"] == 133
    assert parsed.records[0]["lat"] is not None
    assert parsed.records[0]["speed_mps"] == 3.0
    with pytest.raises(FitParseError):
        parse_fit(synthetic_fit(corrupt=True), 10)
    with pytest.raises(FitArchiveError):
        fit_bytes(b"invalid zip")


def test_synthetic_five_minute_interval_fixture():
    parsed = parse_fit(synthetic_fit(five_minutes=True), 10)
    assert len(parsed.records) == 300
    assert [lap["intensity"] for lap in parsed.laps] == ["active", "rest"]
    assert [lap["duration_s"] for lap in parsed.laps] == [150, 150]


def test_timer_stop_preserved_without_interpolation():
    parsed = parse_fit(synthetic_fit(with_pause=True), 10)
    assert [rec["timer_running"] for rec in parsed.records] == [True, False]
    assert len(parsed.records) == 2


def test_fit_download_is_idempotent_and_generates_html(settings, tmp_path):
    pending, counts = pending_fits(settings)
    assert len(pending) == 1 and counts["manual"] == 0

    class FakeClient:
        calls = 0

        def download_activity(self, activity_id):
            self.calls += 1
            return synthetic_zip()

    client = FakeClient()
    assert download_pending(settings, client)["descargado"] == 1
    assert download_pending(settings, client)["descargado"] == 0
    assert client.calls == 1
    result = build_fit(settings)
    assert result["laps"] == 2 and result["records"] == 2 and not result["exceptions"]
    lap_path = settings.silver_dir / "activity_laps.parquet"
    before = lap_path.read_bytes()
    modified = lap_path.stat().st_mtime_ns
    assert build_fit(settings) == result
    assert lap_path.read_bytes() == before
    assert lap_path.stat().st_mtime_ns == modified
    output = tmp_path / "run.html"
    render_run(settings.silver_dir, pending[0]["activity_id"], output)
    assert "Ritmo" in output.read_text() and "Paso workout" in output.read_text()
    laps = pl.read_parquet(settings.silver_dir / "activity_laps.parquet")
    assert laps["wkt_step_index"].to_list() == [0, 1]
    assert not FitWriter(settings.bronze_dir).write(
        pending[0]["activity_id"], date(2026, 10, 20), synthetic_zip()
    )


def test_manual_is_not_downloaded(settings):
    from etl_running.silver.build import activities_path

    path = activities_path(settings.silver_dir)
    df = pl.read_parquet(path).with_columns(is_manual=pl.lit(True))
    df.write_parquet(path)
    pending, excluded = pending_fits(settings)
    assert pending == [] and excluded["manual"] == 1


def test_lap_distance_mismatch_recorded(settings):
    activity_id = pl.read_parquet(settings.silver_dir / "activities.parquet")["activity_id"].item()
    from etl_running.silver.build import activities_path

    path = activities_path(settings.silver_dir)
    pl.read_parquet(path).with_columns(distance_m=pl.lit(2000.0)).write_parquet(path)
    FitWriter(settings.bronze_dir).write(activity_id, date(2026, 10, 20), synthetic_zip())
    result = build_fit(settings)
    assert result["exceptions"][0]["reason"] == "distancia laps vs actividad"
