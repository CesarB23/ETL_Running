from __future__ import annotations

from pathlib import Path

import pytest
from app import queries

from etl_running.demo.warehouse import build_demo_warehouse


@pytest.fixture
def demo_warehouse(tmp_path: Path) -> Path:
    return build_demo_warehouse(tmp_path / "warehouse.duckdb")


def test_snapshot_and_weekly_summary(demo_warehouse: Path):
    snapshot = queries.latest_snapshot(demo_warehouse)
    assert snapshot["last_run_date"] is not None
    assert snapshot["runs_7d"] >= 1
    assert snapshot["km_7d"] > 0
    assert snapshot["acwr_reliable"] is True

    weekly = queries.weekly_summary(demo_warehouse)
    assert not weekly.empty
    assert {"week_start", "run_count", "distance_km", "plan_compliance_pct"} <= set(weekly.columns)


def test_progress_and_load(demo_warehouse: Path):
    progress = queries.progress(120, demo_warehouse)
    assert not progress.empty
    assert progress["pace_min_km"].notna().any()

    load = queries.training_load(120, demo_warehouse)
    assert not load.empty
    assert load["acwr"].notna().any()


def test_plan_queries(demo_warehouse: Path):
    weeks = queries.plan_weeks(demo_warehouse)
    assert weeks
    sessions = queries.plan_sessions(weeks[0], demo_warehouse)
    assert not sessions.empty
    assert "planned_workout_id" in sessions.columns
    blocks = queries.plan_blocks(weeks[0], demo_warehouse)
    assert not blocks.empty
    assert {"pace_status", "actual_pace_s_km", "planned_workout_id"} <= set(blocks.columns)
    summary = queries.plan_week_summary(weeks[0], demo_warehouse)
    assert summary["targeted_steps"] >= 0
    assert "plan_compliance_pct" in summary


def test_data_quality_and_recent_runs(demo_warehouse: Path):
    quality = queries.data_quality(demo_warehouse)
    assert set(quality["dataset"]) == {
        "silver/activities",
        "silver/activity_laps",
        "silver/activity_records",
    }
    recent = queries.recent_runs(5, demo_warehouse)
    assert len(recent) <= 5
    assert recent["km"].gt(0).all()


def test_warehouse_path_demo_mode(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DEMO_LAKE_DIR", str(tmp_path))
    assert queries.warehouse_path() == tmp_path / "warehouse.duckdb"
    monkeypatch.setenv("DEMO_MODE", "0")
    assert queries.warehouse_path() == Path("lake/warehouse.duckdb")


def test_missing_warehouse_raises(tmp_path: Path):
    with pytest.raises(queries.DashboardError):
        queries.weekly_summary(tmp_path / "missing.duckdb")
