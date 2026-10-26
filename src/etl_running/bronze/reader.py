"""Lectura de bronze: última versión de cada partición."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from etl_running.bronze.writer import BronzeWriter


@dataclass(frozen=True)
class BronzeRecord:
    raw: dict[str, Any]
    ingested_at: datetime
    run_id: str
    path: str
    dt: date


def read_latest_records(
    bronze_dir: Path, source: str = "garmin", dataset: str = "activities_list"
) -> list[BronzeRecord]:
    """Registros de la última versión de cada `dt` (las anteriores quedan como historial)."""
    latest: dict[date, dict[str, Any]] = {}
    for row in BronzeWriter(bronze_dir).read_manifest().to_pylist():
        if row["source"] != source or row["dataset"] != dataset:
            continue
        current = latest.get(row["dt"])
        if current is None or (row["ingested_at"], row["run_id"]) > (
            current["ingested_at"],
            current["run_id"],
        ):
            latest[row["dt"]] = row

    records: list[BronzeRecord] = []
    for dt in sorted(latest):
        row = latest[dt]
        payload = json.loads((bronze_dir / row["path"]).read_text(encoding="utf-8"))
        records.extend(
            BronzeRecord(item, row["ingested_at"], row["run_id"], row["path"], dt)
            for item in payload
        )
    return records


def manifest_fingerprint(bronze_dir: Path) -> str:
    """Huella del manifiesto completo: cambia si llega cualquier archivo nuevo."""
    rows = BronzeWriter(bronze_dir).read_manifest().to_pylist()
    lines = sorted(f"{r['path']}:{r['sha256']}" for r in rows)
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()
