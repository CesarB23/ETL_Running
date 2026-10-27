"""Construye Silver planned_workouts/steps desde los JSON versionados de bronze."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import polars as pl

from etl_running.bronze.reader import read_latest_records
from etl_running.common.config import Settings
from etl_running.silver.build import _atomic_json, _atomic_parquet
from etl_running.silver.parsers.plan import parse_week

LOGGER = logging.getLogger("etl_running.silver.plan")
PLAN_BUILD_VERSION = "2"
WORKOUT_SCHEMA = {
    "planned_workout_id": pl.Utf8,
    "week_start": pl.Date,
    "scheduled_date": pl.Date,
    "title": pl.Utf8,
    "plan_hash": pl.Utf8,
    "garmin_workout_id": pl.Int64,
    "garmin_workout_name": pl.Utf8,
}
STEP_SCHEMA = {
    "planned_workout_id": pl.Utf8,
    "step_seq": pl.Int64,
    "step_order": pl.Int64,
    "candidate_fit_index": pl.Int64,
    "kind": pl.Utf8,
    "repetition": pl.Int64,
    "target_distance_m": pl.Float64,
    "target_duration_s": pl.Float64,
    "pace_fast_s_km": pl.Float64,
    "pace_slow_s_km": pl.Float64,
    "speed_min_mps": pl.Float64,
    "speed_max_mps": pl.Float64,
}
LINK_SCHEMA = {
    "activity_id": pl.Int64,
    "planned_workout_id": pl.Utf8,
    "garmin_workout_id": pl.Int64,
    "match_method": pl.Utf8,
}
CONFIRMATION_SCHEMA = {
    "planned_workout_id": pl.Utf8,
    "activity_id": pl.Int64,
    "plan_hash": pl.Utf8,
    "confirmed_at": pl.Datetime("us", "UTC"),
}


def build_plan(settings: Settings, uploads_path: Path | None = None) -> dict:
    """Los uploads reales son *opcionalmente leídos*, nunca copiados ni versionados."""
    uploads = {}
    if uploads_path and uploads_path.is_file():
        payload = json.loads(uploads_path.read_text(encoding="utf-8"))
        uploads = payload.get("workouts") or {}
        if not isinstance(uploads, dict):
            raise ValueError("uploads.workouts debe ser un objeto por fecha")
    records = read_latest_records(settings.bronze_dir, "plan", "weekly_plan")
    fingerprint = hashlib.sha256(
        (
            f"plan-v{PLAN_BUILD_VERSION}|"
            + "|".join(f"{r.path}:{r.ingested_at.isoformat()}" for r in records)
            + "|"
            + hashlib.sha256(json.dumps(uploads, sort_keys=True).encode()).hexdigest()
        ).encode()
    ).hexdigest()
    root = settings.silver_dir
    meta = root / "_plan_build.json"
    if not (root / "activity_workout_links.parquet").is_file():
        _atomic_parquet(pl.DataFrame(schema=LINK_SCHEMA), root / "activity_workout_links.parquet")
    if not (root / "plan_confirmations.parquet").is_file():
        _atomic_parquet(
            pl.DataFrame(schema=CONFIRMATION_SCHEMA), root / "plan_confirmations.parquet"
        )
    if (
        meta.is_file()
        and (root / "planned_workouts.parquet").is_file()
        and (root / "planned_steps.parquet").is_file()
    ):
        previous = json.loads(meta.read_text(encoding="utf-8"))
        if previous.get("fingerprint") == fingerprint:
            LOGGER.info("Plan sin cambios: Silver al día")
            return previous
    workouts, steps = [], []
    for record in records:
        week_workouts, week_steps = parse_week(record.raw, uploads)
        workouts.extend(week_workouts)
        steps.extend(week_steps)
    if len({r["planned_workout_id"] for r in workouts}) != len(workouts):
        raise ValueError("Sesiones de plan duplicadas entre semanas")
    _atomic_parquet(
        pl.DataFrame(workouts, schema=WORKOUT_SCHEMA).sort("planned_workout_id"),
        root / "planned_workouts.parquet",
    )
    _atomic_parquet(
        pl.DataFrame(steps, schema=STEP_SCHEMA).sort("planned_workout_id", "step_seq"),
        root / "planned_steps.parquet",
    )
    result = {
        "weeks": len(records),
        "sessions": len(workouts),
        "steps": len(steps),
        "uploaded_ids": sum(w["garmin_workout_id"] is not None for w in workouts),
        "fingerprint": fingerprint,
    }
    _atomic_json(result, meta)
    LOGGER.info(
        "Plan Silver: %d semanas, %d sesiones, %d pasos, %d IDs Garmin",
        result["weeks"],
        result["sessions"],
        result["steps"],
        result["uploaded_ids"],
    )
    return result
