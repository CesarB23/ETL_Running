"""Contrato Pandera de `silver.activities`."""

from __future__ import annotations

from collections.abc import Iterable

import pandera.polars as pa
import polars as pl

UTC_TS = pl.Datetime("us", "UTC")
SCHEMA_VERSION = "1"

ACTIVITIES_POLARS_SCHEMA: dict[str, pl.DataType] = {
    "activity_id": pl.Int64,
    "activity_type": pl.Utf8,
    "is_manual": pl.Boolean,
    "has_gps": pl.Boolean,
    "start_utc": UTC_TS,
    "start_local": pl.Datetime("us"),
    "local_date": pl.Date,
    "tz_local": pl.Utf8,
    "utc_offset_min": pl.Int32,
    "distance_m": pl.Float64,
    "duration_s": pl.Float64,
    "moving_s": pl.Float64,
    "elapsed_s": pl.Float64,
    "avg_speed_mps": pl.Float64,
    "max_speed_mps": pl.Float64,
    "avg_hr": pl.Float64,
    "max_hr": pl.Float64,
    "avg_cadence_spm": pl.Float64,
    "stride_m": pl.Float64,
    "elev_gain_m": pl.Float64,
    "elev_loss_m": pl.Float64,
    "calories": pl.Float64,
    "lap_count": pl.Int64,
    "moderate_intensity_min": pl.Int64,
    "vigorous_intensity_min": pl.Int64,
    "start_lat": pl.Float64,
    "start_lon": pl.Float64,
    "bronze_run_id": pl.Utf8,
    "bronze_ingested_at": UTC_TS,
    "source_path": pl.Utf8,
}

QUARANTINE_POLARS_SCHEMA: dict[str, pl.DataType] = {
    "activity_id": pl.Int64,
    "reason": pl.Utf8,
    "source_path": pl.Utf8,
    "bronze_run_id": pl.Utf8,
    "bronze_ingested_at": UTC_TS,
}

_NULLABLE = {
    "distance_m", "moving_s", "elapsed_s", "avg_speed_mps", "max_speed_mps",
    "avg_hr", "max_hr", "avg_cadence_spm", "stride_m", "elev_gain_m", "elev_loss_m",
    "calories", "lap_count", "moderate_intensity_min", "vigorous_intensity_min",
    "start_lat", "start_lon",
}  # fmt: skip

_CHECKS: dict[str, list[pa.Check]] = {
    "distance_m": [pa.Check.ge(0)],
    "duration_s": [pa.Check.gt(0)],
    "moving_s": [pa.Check.ge(0)],
    "elapsed_s": [pa.Check.ge(0)],
    "avg_speed_mps": [pa.Check.ge(0)],
    "max_speed_mps": [pa.Check.ge(0)],
    "avg_hr": [pa.Check.in_range(30, 230)],
    "max_hr": [pa.Check.in_range(30, 230)],
    "avg_cadence_spm": [pa.Check.in_range(0, 300)],
    "stride_m": [pa.Check.in_range(0, 4)],
    "elev_gain_m": [pa.Check.ge(0)],
    "elev_loss_m": [pa.Check.ge(0)],
    "calories": [pa.Check.ge(0)],
    "lap_count": [pa.Check.ge(0)],
    "moderate_intensity_min": [pa.Check.ge(0)],
    "vigorous_intensity_min": [pa.Check.ge(0)],
    "start_lat": [pa.Check.in_range(-90, 90)],
    "start_lon": [pa.Check.in_range(-180, 180)],
}


def activities_schema(running_type_keys: Iterable[str]) -> pa.DataFrameSchema:
    """Tipos, nulabilidad, rangos, unicidad y `activity_type ∈ RUNNING_TYPE_KEYS`."""
    allowed = list(running_type_keys)
    columns: dict[str, pa.Column] = {}
    for name, dtype in ACTIVITIES_POLARS_SCHEMA.items():
        checks = list(_CHECKS.get(name, []))
        if name == "activity_type":
            checks.append(pa.Check.isin(allowed))
        columns[name] = pa.Column(
            dtype,
            checks=checks or None,
            nullable=name in _NULLABLE,
            unique=name == "activity_id",
        )
    return pa.DataFrameSchema(columns, strict=True, ordered=True)
