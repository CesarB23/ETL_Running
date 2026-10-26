"""Reconstruye laps y records desde los ZIP FIT en bronze."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import polars as pl

from etl_running.bronze.fit import FitArchiveError, fit_bytes
from etl_running.bronze.writer import BronzeWriter
from etl_running.common.config import Settings
from etl_running.silver.build import _atomic_json, _atomic_parquet, activities_path
from etl_running.silver.parsers.fit import FitParseError, parse_fit

LOGGER = logging.getLogger("etl_running.silver.fit")
FIT_BUILD_VERSION = "2"
UTC_TS = pl.Datetime("us", "UTC")
LAPS_SCHEMA = {
    "activity_id": pl.Int64,
    "lap_index": pl.Int64,
    "start_utc": UTC_TS,
    "end_utc": UTC_TS,
    "distance_m": pl.Float64,
    "duration_s": pl.Float64,
    "elapsed_s": pl.Float64,
    "avg_speed_mps": pl.Float64,
    "avg_hr": pl.Float64,
    "max_hr": pl.Float64,
    "avg_cadence_spm": pl.Float64,
    "elev_gain_m": pl.Float64,
    "lap_trigger": pl.Utf8,
    "intensity": pl.Utf8,
    "wkt_step_index": pl.Int64,
}
RECORDS_SCHEMA = {
    "activity_id": pl.Int64,
    "ts_utc": UTC_TS,
    "distance_m": pl.Float64,
    "speed_mps": pl.Float64,
    "heart_rate": pl.Int64,
    "cadence_spm": pl.Int64,
    "altitude_m": pl.Float64,
    "lat": pl.Float64,
    "lon": pl.Float64,
    "timer_running": pl.Boolean,
}


def build_fit(settings: Settings, tolerance: float = 0.01) -> dict:
    """Idempotente: tablas derivadas por reemplazo atómico; excepciones documentadas."""
    if not 0 < tolerance < 1:
        raise ValueError("tolerance debe estar entre 0 y 1")
    activities = pl.read_parquet(activities_path(settings.silver_dir))
    distances = {r["activity_id"]: r["distance_m"] for r in activities.iter_rows(named=True)}
    files = [
        r
        for r in BronzeWriter(settings.bronze_dir).read_manifest().to_pylist()
        if r["source"] == "garmin" and r["dataset"] == "activity_fit"
    ]
    fingerprint = hashlib.sha256(
        (
            f"{FIT_BUILD_VERSION}|{tolerance}|"
            + hashlib.sha256(activities_path(settings.silver_dir).read_bytes()).hexdigest()
            + "|"
            + "|".join(sorted(f"{row['path']}:{row['sha256']}" for row in files))
        ).encode()
    ).hexdigest()
    summary_path = settings.silver_dir / "_fit_build.json"
    if (
        summary_path.is_file()
        and (settings.silver_dir / "activity_laps.parquet").is_file()
        and (settings.silver_dir / "activity_records.parquet").is_file()
    ):
        previous = json.loads(summary_path.read_text(encoding="utf-8"))
        if previous.get("fingerprint") == fingerprint:
            LOGGER.info("FIT y Silver sin cambios: laps y records ya están al día")
            return previous
    laps, records, issues = [], [], []
    for entry in sorted(files, key=lambda r: r["path"]):
        activity_id = int(Path(entry["path"]).stem)
        if activity_id not in distances:
            continue  # Silver es autoridad del alcance running.
        path = settings.bronze_dir / entry["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            issues.append({"activity_id": activity_id, "reason": "checksum incorrecto"})
            continue
        try:
            parsed = parse_fit(fit_bytes(path.read_bytes()), activity_id)
        except (FitArchiveError, FitParseError) as exc:
            issues.append({"activity_id": activity_id, "reason": type(exc).__name__})
            continue
        expected = distances[activity_id]
        if parsed.laps and expected and all(lap["distance_m"] is not None for lap in parsed.laps):
            delta = abs(sum(lap["distance_m"] for lap in parsed.laps) - expected) / expected
            if delta >= tolerance:
                issues.append(
                    {
                        "activity_id": activity_id,
                        "reason": "distancia laps vs actividad",
                        "relative_delta": round(delta, 4),
                    }
                )
        elif not parsed.laps:
            issues.append({"activity_id": activity_id, "reason": "sin laps"})
        laps.extend(parsed.laps)
        records.extend(parsed.records)
        LOGGER.info(
            "Actividad %d: %d laps, %d records, %d eventos timer",
            activity_id,
            len(parsed.laps),
            len(parsed.records),
            len(parsed.events),
        )
    silver = settings.silver_dir
    lap_df = pl.DataFrame(laps, schema=LAPS_SCHEMA).sort("activity_id", "lap_index")
    rec_df = pl.DataFrame(records, schema=RECORDS_SCHEMA).sort("activity_id", "ts_utc")
    _atomic_parquet(lap_df, silver / "activity_laps.parquet")
    _atomic_parquet(rec_df, silver / "activity_records.parquet")
    result = {
        "fits": len(files),
        "laps": lap_df.height,
        "records": rec_df.height,
        "exceptions": issues,
        "fingerprint": fingerprint,
    }
    _atomic_json(result, summary_path)
    LOGGER.info(
        "FIT procesados: %d | laps: %d | records: %d | excepciones: %d",
        len(files),
        lap_df.height,
        rec_df.height,
        len(issues),
    )
    return result
