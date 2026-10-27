"""Plan totalmente sintético; no lee ../Garmin ni datos personales."""

from __future__ import annotations

import json
from datetime import date

import polars as pl
import pytest

from etl_running.bronze.writer import BronzeWriter
from etl_running.common.config import Settings
from etl_running.ingest.plan_loader import PlanError, load_week
from etl_running.silver.parsers.plan import parse_week
from etl_running.silver.plan_build import build_plan
from etl_running.silver.plan_confirmations import confirm_match
from etl_running.silver.plan_links import collect_links


def sample_week():
    return {
        "version": 1,
        "week_start": "2026-10-19",
        "week_end": "2026-10-25",
        "sessions": [
            {
                "date": "2026-10-20",
                "title": "Series ficticias",
                "blocks": [
                    {"kind": "warmup", "duration_s": 300},
                    {
                        "kind": "reps",
                        "reps": 2,
                        "distance_m": 1000,
                        "pace_s_km": [300, 320],
                        "recovery": {"kind": "time", "seconds": 90},
                    },
                    {"kind": "cooldown", "duration_s": 120},
                ],
            },
            {
                "date": "2026-10-22",
                "title": "Continuo ficticio",
                "blocks": [{"kind": "continuous", "distance_m": 1000, "pace_s_km": [300, 340]}],
            },
            {
                "date": "2026-10-24",
                "title": "Progresivo ficticio",
                "blocks": [{"kind": "steady", "duration_s": 600, "pace_s_km": [340, 360]}],
            },
        ],
        "skipped": [
            {"date": "2026-10-21", "reason": "fuerza"},
            {"date": "2026-10-23", "reason": "descanso"},
        ],
    }


def test_step_expansion_repeats_and_speed_conversion():
    workouts, steps = parse_week(sample_week(), {"2026-10-20": {"workoutId": 123}})
    assert len(workouts) == 3
    assert workouts[0]["garmin_workout_id"] == 123
    assert [s["kind"] for s in steps[:6]] == [
        "warmup",
        "work",
        "recovery",
        "work",
        "recovery",
        "cooldown",
    ]
    assert [s["step_order"] for s in steps[:6]] == [1, 3, 4, 3, 4, 5]
    assert steps[1]["speed_min_mps"] == pytest.approx(1000 / 320)
    assert steps[1]["speed_max_mps"] == pytest.approx(1000 / 300)
    assert steps[2]["speed_min_mps"] is None
    assert all(s["step_seq"] == i for i, s in enumerate(steps[:6]))


def test_week_load_is_idempotent_and_silver_rebuild(tmp_path):
    settings = Settings(lake_dir=tmp_path / "lake")
    path = tmp_path / "week.json"
    path.write_text(json.dumps(sample_week()))
    assert load_week(settings, path)
    manifest = BronzeWriter(settings.bronze_dir).read_manifest().to_pylist()
    assert not load_week(settings, path)
    assert BronzeWriter(settings.bronze_dir).read_manifest().to_pylist() == manifest
    upload = tmp_path / "uploads.json"
    upload.write_text(json.dumps({"workouts": {"2026-10-20": {"workoutId": 123}}}))
    first = build_plan(settings, upload)
    assert first["weeks"] == 1 and first["sessions"] == 3 and first["uploaded_ids"] == 1
    path = settings.silver_dir / "planned_steps.parquet"
    modified = path.stat().st_mtime_ns
    assert build_plan(settings, upload) == first
    assert path.stat().st_mtime_ns == modified
    assert pl.read_parquet(path)["planned_workout_id"].n_unique() == 3
    with pytest.raises(PlanError):
        invalid = sample_week()
        invalid["week_start"] = "2026-10-20"
        wrong = tmp_path / "wrong.json"
        wrong.write_text(json.dumps(invalid))
        load_week(settings, wrong)


def test_invalid_earlier_week_rejected(tmp_path):
    settings = Settings(lake_dir=tmp_path / "lake")
    invalid = sample_week()
    invalid["week_start"] = "2026-08-10"
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps(invalid))
    with pytest.raises(ValueError, match="anterior"):
        load_week(settings, path)


def test_workout_link_requires_exact_api_name_and_is_idempotent(tmp_path):
    settings = Settings(lake_dir=tmp_path / "lake")
    path = tmp_path / "week.json"
    path.write_text(json.dumps(sample_week()))
    load_week(settings, path)
    uploads = tmp_path / "uploads.json"
    uploads.write_text(
        json.dumps(
            {"workouts": {"2026-10-20": {"workoutId": 123, "name": "Serie ficticia Garmin"}}}
        )
    )
    build_plan(settings, uploads)
    pl.DataFrame(
        [{"activity_id": 42, "local_date": date(2026, 10, 20), "is_manual": False}]
    ).write_parquet(settings.silver_dir / "activities.parquet")

    class FakeClient:
        calls = 0

        def get_activity_workouts(self, activity_id):
            self.calls += 1
            assert activity_id == 42
            return [{"workoutName": "Serie ficticia Garmin"}]

    fake = FakeClient()
    assert collect_links(settings, fake) == 1
    assert collect_links(settings, fake) == 1
    assert fake.calls == 1
    links = pl.read_parquet(settings.silver_dir / "activity_workout_links.parquet")
    assert links["garmin_workout_id"].item() == 123

    class WrongName(FakeClient):
        def get_activity_workouts(self, activity_id):
            return [{"workoutName": "Otro workout"}]

    assert collect_links(settings, WrongName(), refresh=True) == 0


def test_manual_confirmation_validates_date_and_reuses_same_match(tmp_path):
    settings = Settings(lake_dir=tmp_path / "lake")
    source = tmp_path / "week.json"
    source.write_text(json.dumps(sample_week()))
    load_week(settings, source)
    build_plan(settings)
    pl.DataFrame(
        [
            {"activity_id": 10, "local_date": date(2026, 10, 21), "is_manual": False},
            {"activity_id": 11, "local_date": date(2026, 10, 25), "is_manual": False},
        ]
    ).write_parquet(settings.silver_dir / "activities.parquet")
    (settings.silver_dir / "plan_confirmations.parquet").unlink()
    assert confirm_match(settings, date(2026, 10, 20), 10)
    assert not confirm_match(settings, date(2026, 10, 20), 10)
    row = pl.read_parquet(settings.silver_dir / "plan_confirmations.parquet").row(0, named=True)
    assert row["plan_hash"] and row["activity_id"] == 10
    with pytest.raises(ValueError, match="ventana"):
        confirm_match(settings, date(2026, 10, 22), 11)
    with pytest.raises(ValueError, match="otra sesión"):
        confirm_match(settings, date(2026, 10, 22), 10)
