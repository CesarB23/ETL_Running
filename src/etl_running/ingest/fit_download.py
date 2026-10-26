"""Descarga FIT solo de carreras elegibles, con reintentos del cliente Garmin."""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from etl_running.bronze.fit import FitArchiveError, FitWriter
from etl_running.common.config import Settings
from etl_running.silver.build import activities_path

LOGGER = logging.getLogger("etl_running.ingest.fit")


def pending_fits(settings: Settings) -> tuple[list[dict[str, Any]], Counter[str]]:
    """Actividades silver sin FIT; motivo de exclusión sin falsear ausencias."""
    path = activities_path(settings.silver_dir)
    if not path.is_file():
        raise FileNotFoundError("Falta Silver: ejecuta `etl_running silver build` primero")
    present = FitWriter(settings.bronze_dir).present_ids()
    excluded: Counter[str] = Counter()
    pending = []
    for row in pl.read_parquet(path).sort("start_utc").iter_rows(named=True):
        if row["activity_id"] in present:
            excluded["ya_descargado"] += 1
        elif row["is_manual"]:
            excluded["manual"] += 1
        elif row["activity_type"] == "treadmill_running" and not row["avg_hr"]:
            excluded["cinta_sin_sensor"] += 1
        elif not row["has_gps"] and not row["avg_hr"]:
            excluded["sin_gps_ni_fc"] += 1
        else:
            pending.append(row)
    return pending, excluded


def _save_status(path: Path, status: dict[str, str]) -> None:
    """Solo estado operativo, sin contenido FIT ni secretos."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as out:
        out.write(json.dumps(status, ensure_ascii=False) + "\n")


def download_pending(settings: Settings, client: Any) -> Counter[str]:
    """Descarga pendientes uno a uno. 404/403 se registran, otros fallos se propagan."""
    pending, counts = pending_fits(settings)
    writer = FitWriter(settings.bronze_dir)
    status_path = settings.lake_dir / "_state" / "fit_download.jsonl"
    LOGGER.info("FIT pendientes: %d (excluidas: %s)", len(pending), dict(counts))
    for index, row in enumerate(pending, start=1):
        activity_id = row["activity_id"]
        LOGGER.info("FIT %d/%d: descarga de actividad %d", index, len(pending), activity_id)
        try:
            data = client.download_activity(activity_id)
            if writer.write(activity_id, row["local_date"], data):
                counts["descargado"] += 1
                LOGGER.info("FIT descargado (%d bytes)", len(data))
            else:
                counts["ya_descargado"] += 1
        except Exception as exc:
            code = getattr(exc, "status_code", None)
            if code not in (403, 404) and not isinstance(exc, FitArchiveError):
                raise
            reason = f"HTTP {code}" if code else type(exc).__name__
            counts["sin_descarga"] += 1
            _save_status(
                status_path,
                {
                    "activity_id": str(activity_id),
                    "reason": reason,
                    "ts_utc": datetime.now(UTC).isoformat(),
                },
            )
            LOGGER.warning("FIT no disponible (actividad %d, %s)", activity_id, reason)
    return counts
