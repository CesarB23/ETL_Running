"""Construcción de `silver.activities` desde bronze (reconstruible y determinista)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandera.errors
import polars as pl

from etl_running.bronze.reader import BronzeRecord, manifest_fingerprint, read_latest_records
from etl_running.common.config import Settings
from etl_running.silver.parsers.activities import PARSER_VERSION, ParseError, parse_activity
from etl_running.silver.schemas import (
    ACTIVITIES_POLARS_SCHEMA,
    QUARANTINE_POLARS_SCHEMA,
    SCHEMA_VERSION,
    activities_schema,
)

LOGGER = logging.getLogger("etl_running.silver")

SUMMARY_NAME = "_build.json"
PARQUET_COMPRESSION = "uncompressed"  # Compatible con visores básicos de Parquet.


def activities_path(silver_dir: Path) -> Path:
    return silver_dir / "activities.parquet"


def quarantine_path(silver_dir: Path) -> Path:
    return silver_dir / "_quarantine" / "activities.parquet"


def summary_path(silver_dir: Path) -> Path:
    return silver_dir / SUMMARY_NAME


@dataclass
class BuildResult:
    built_at: str = ""
    skipped: bool = False
    wrote: bool = False
    bronze_records: int = 0
    duplicates_dropped: int = 0
    bronze_unique: int = 0
    silver: int = 0
    quarantine: int = 0
    out_of_scope: dict[str, int] = field(default_factory=dict)
    warnings: int = 0
    table_hash: str = ""
    fingerprint: str = ""

    @property
    def out_of_scope_total(self) -> int:
        return sum(self.out_of_scope.values())

    @property
    def reconciles(self) -> bool:
        return self.bronze_unique == self.silver + self.quarantine + self.out_of_scope_total


def table_hash(df: pl.DataFrame) -> str:
    """Hash lógico: mismo contenido → mismo hash, sin depender del archivo Parquet."""
    ordered = df.sort("activity_id") if df.height else df
    return hashlib.sha256(ordered.write_csv().encode()).hexdigest()


def _fingerprint(settings: Settings) -> str:
    base = manifest_fingerprint(settings.bronze_dir)
    extra = (
        f"{PARSER_VERSION}|{SCHEMA_VERSION}|{PARQUET_COMPRESSION}|"
        f"{','.join(settings.running_type_keys)}"
    )
    return hashlib.sha256(f"{base}|{extra}".encode()).hexdigest()


def _atomic_parquet(df: pl.DataFrame, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    os.close(fd)
    try:
        df.write_parquet(tmp, compression=PARQUET_COMPRESSION)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _atomic_json(data: dict[str, Any], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_summary(silver_dir: Path) -> BuildResult | None:
    path = summary_path(silver_dir)
    if not path.is_file():
        return None
    return BuildResult(**json.loads(path.read_text(encoding="utf-8")))


def _dedupe(records: list[BronzeRecord]) -> tuple[list[BronzeRecord], int]:
    """Una versión por `activityId`: gana la de mayor `ingested_at`. Sin id → se conservan."""
    best: dict[Any, BronzeRecord] = {}
    no_id: list[BronzeRecord] = []
    for rec in records:
        activity_id = rec.raw.get("activityId")
        if not isinstance(activity_id, int) or isinstance(activity_id, bool):
            no_id.append(rec)
            continue
        current = best.get(activity_id)
        if current is None or (rec.ingested_at, rec.run_id) > (current.ingested_at, current.run_id):
            best[activity_id] = rec
    kept = [*best.values(), *no_id]
    return kept, len(records) - len(kept)


def _quarantine_row(rec: BronzeRecord, reason: str) -> dict[str, Any]:
    activity_id = rec.raw.get("activityId")
    return {
        "activity_id": activity_id
        if isinstance(activity_id, int) and not isinstance(activity_id, bool)
        else None,
        "reason": reason,
        "source_path": rec.path,
        "bronze_run_id": rec.run_id,
        "bronze_ingested_at": rec.ingested_at,
    }


def _validate(
    df: pl.DataFrame, records: list[BronzeRecord], settings: Settings
) -> tuple[pl.DataFrame, list[dict[str, Any]]]:
    """Valida el contrato; las filas que fallan van a cuarentena con su motivo."""
    schema = activities_schema(settings.running_type_keys)
    try:
        return schema.validate(df, lazy=True), []
    except pandera.errors.SchemaErrors as exc:
        cases = exc.failure_cases
        if cases["index"].null_count():
            raise  # fallo de esquema global (no atribuible a una fila): es un bug, no un dato
        reasons: dict[int, list[str]] = {}
        for case in cases.iter_rows(named=True):
            reasons.setdefault(case["index"], []).append(f"{case['column']}: {case['check']}")
    bad = sorted(reasons)
    quarantined = [_quarantine_row(records[i], "; ".join(reasons[i])) for i in bad]
    keep = df.with_row_index("_i").filter(~pl.col("_i").is_in(bad)).drop("_i")
    return schema.validate(keep), quarantined


def build_silver(settings: Settings, *, full_refresh: bool = False) -> BuildResult:
    t0 = time.monotonic()
    silver_dir = settings.silver_dir
    LOGGER.info("===== INICIO silver.activities | full_refresh=%s =====", full_refresh)

    LOGGER.info("Paso 1/5 · Comprobar si bronze cambió desde la última construcción")
    fingerprint = _fingerprint(settings)
    previous = load_summary(silver_dir)
    if (
        not full_refresh
        and previous
        and previous.fingerprint == fingerprint
        and activities_path(silver_dir).is_file()
        and quarantine_path(silver_dir).is_file()
    ):
        previous.skipped = True
        previous.wrote = False
        LOGGER.info(
            "Bronze sin cambios (huella %s…). Silver ya está al día: nada que hacer.",
            fingerprint[:8],
        )
        LOGGER.info(
            "===== FIN silver.activities | SIN CAMBIOS | %.1f s =====", time.monotonic() - t0
        )
        return previous
    if full_refresh:
        LOGGER.info("--full-refresh: se reconstruye todo desde bronze ignorando el estado previo.")

    LOGGER.info("Paso 2/5 · Leer bronze (última versión de cada partición) y deduplicar")
    records = read_latest_records(settings.bronze_dir)
    unique, dropped = _dedupe(records)
    LOGGER.info(
        "Bronze: %d registros leídos, %d versiones antiguas descartadas, %d actividades únicas.",
        len(records),
        dropped,
        len(unique),
    )

    LOGGER.info(
        "Paso 3/5 · Filtrar alcance (RUNNING_TYPE_KEYS = %s)", ",".join(settings.running_type_keys)
    )
    in_scope: list[BronzeRecord] = []
    out_of_scope: Counter[str] = Counter()
    for rec in unique:
        activity_type = rec.raw.get("activityType")
        type_key = activity_type.get("typeKey") if isinstance(activity_type, dict) else None
        if type_key is not None and type_key not in settings.running_type_keys:
            out_of_scope[type_key] += 1
        else:
            in_scope.append(rec)
    LOGGER.info(
        "En alcance: %d. Fuera de alcance (out_of_scope): %d [%s]",
        len(in_scope),
        sum(out_of_scope.values()),
        ", ".join(f"{k}={v}" for k, v in out_of_scope.most_common()) or "ninguno",
    )

    LOGGER.info("Paso 4/5 · Parsear y validar contrato (Pandera)")
    rows: list[dict[str, Any]] = []
    parsed_records: list[BronzeRecord] = []
    quarantined: list[dict[str, Any]] = []
    warnings = 0
    for rec in sorted(in_scope, key=lambda r: str(r.raw.get("activityId"))):
        try:
            parsed = parse_activity(rec.raw)
        except ParseError as exc:
            LOGGER.warning(
                "Cuarentena: actividad %s (%s): %s", rec.raw.get("activityId"), rec.path, exc
            )
            quarantined.append(_quarantine_row(rec, f"parse: {exc}"))
            continue
        for message in parsed.warnings:
            warnings += 1
            LOGGER.warning("Actividad %s: %s", parsed.row["activity_id"], message)
        rows.append(
            {
                **parsed.row,
                "bronze_run_id": rec.run_id,
                "bronze_ingested_at": rec.ingested_at,
                "source_path": rec.path,
            }
        )
        parsed_records.append(rec)

    df = pl.DataFrame(rows, schema=ACTIVITIES_POLARS_SCHEMA)
    df, invalid = _validate(df, parsed_records, settings)
    for item in invalid:
        LOGGER.warning(
            "Cuarentena: actividad %s (%s): %s",
            item["activity_id"],
            item["source_path"],
            item["reason"],
        )
    quarantined.extend(invalid)
    df = df.sort("activity_id")
    digest = table_hash(df)
    LOGGER.info(
        "Válidas: %d. En cuarentena: %d. Avisos (valores → NULL): %d.",
        df.height,
        len(quarantined),
        warnings,
    )

    LOGGER.info("Paso 5/5 · Escribir Parquet")
    unchanged = (
        not full_refresh
        and previous is not None
        and previous.fingerprint == fingerprint
        and previous.table_hash == digest
        and activities_path(silver_dir).is_file()
    )
    if unchanged:
        LOGGER.info(
            "El contenido lógico no cambió (hash %s…): no se reescribe la tabla.", digest[:8]
        )
    else:
        _atomic_parquet(df, activities_path(silver_dir))
        LOGGER.info(
            "Escrito %s (%d filas, hash %s…)", activities_path(silver_dir), df.height, digest[:8]
        )
    _atomic_parquet(
        pl.DataFrame(quarantined, schema=QUARANTINE_POLARS_SCHEMA), quarantine_path(silver_dir)
    )

    result = BuildResult(
        built_at=datetime.now(UTC).isoformat(),
        skipped=False,
        wrote=not unchanged,
        bronze_records=len(records),
        duplicates_dropped=dropped,
        bronze_unique=len(unique),
        silver=df.height,
        quarantine=len(quarantined),
        out_of_scope=dict(out_of_scope),
        warnings=warnings,
        table_hash=digest,
        fingerprint=fingerprint,
    )
    _atomic_json(asdict(result), summary_path(silver_dir))
    LOGGER.info(
        "Reconciliación: %d únicas en bronze = %d silver + %d cuarentena + %d out_of_scope → %s",
        result.bronze_unique,
        result.silver,
        result.quarantine,
        result.out_of_scope_total,
        "OK" if result.reconciles else "NO CUADRA",
    )
    LOGGER.info("===== FIN silver.activities | OK | %.1f s =====", time.monotonic() - t0)
    return result
