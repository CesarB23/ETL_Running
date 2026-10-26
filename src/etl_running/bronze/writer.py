"""Escritura de bronze: inmutable, atómica e idempotente por hash."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

MANIFEST_NAME = "_manifest.parquet"
MANIFEST_SCHEMA = pa.schema(
    [
        ("source", pa.string()),
        ("dataset", pa.string()),
        ("dt", pa.date32()),
        ("run_id", pa.string()),
        ("path", pa.string()),
        ("sha256", pa.string()),
        ("n_records", pa.int64()),
        ("n_bytes", pa.int64()),
        ("ingested_at", pa.timestamp("us", tz="UTC")),
    ]
)


def new_run_id(now: datetime | None = None) -> str:
    """`YYYYMMDDTHHMMSSZ-xxxxxx`: timestamp UTC + sufijo aleatorio corto."""
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{secrets.token_hex(3)}"


def canonical_bytes(payload: list[dict[str, Any]]) -> bytes:
    """Serialización determinista (claves ordenadas, actividades ordenadas por id)."""
    ordered = sorted(payload, key=lambda a: str(a.get("activityId", "")))
    return json.dumps(ordered, ensure_ascii=False, sort_keys=True, indent=1).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class WriteResult:
    dt: date
    written: bool
    path: Path | None
    sha256: str
    n_records: int


class BronzeWriter:
    def __init__(self, bronze_dir: Path) -> None:
        self.root = bronze_dir

    @property
    def manifest_path(self) -> Path:
        return self.root / MANIFEST_NAME

    def read_manifest(self) -> pa.Table:
        if not self.manifest_path.is_file():
            return MANIFEST_SCHEMA.empty_table()
        return pq.read_table(self.manifest_path).cast(MANIFEST_SCHEMA)

    def latest_sha(self, source: str, dataset: str, dt: date) -> str | None:
        rows = [
            r
            for r in self.read_manifest().to_pylist()
            if r["source"] == source and r["dataset"] == dataset and r["dt"] == dt
        ]
        if not rows:
            return None
        return max(rows, key=lambda r: r["ingested_at"])["sha256"]

    def write_partition(
        self,
        source: str,
        dataset: str,
        dt: date,
        payload: list[dict[str, Any]],
        run_id: str,
    ) -> WriteResult:
        """Escribe `payload` solo si su hash difiere del último de esa partición."""
        data = canonical_bytes(payload)
        digest = sha256_hex(data)
        if self.latest_sha(source, dataset, dt) == digest:
            return WriteResult(dt, False, None, digest, len(payload))

        target = self.root / source / dataset / f"dt={dt.isoformat()}" / f"{run_id}.json"
        if target.exists():
            raise FileExistsError(f"Bronze es inmutable; ya existe {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(target, data)
        self._append_manifest(
            {
                "source": source,
                "dataset": dataset,
                "dt": dt,
                "run_id": run_id,
                "path": str(target.relative_to(self.root)),
                "sha256": digest,
                "n_records": len(payload),
                "n_bytes": len(data),
                "ingested_at": datetime.now(UTC),
            }
        )
        return WriteResult(dt, True, target, digest, len(payload))

    @staticmethod
    def _atomic_write(target: Path, data: bytes) -> None:
        fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp, target)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def _append_manifest(self, row: dict[str, Any]) -> None:
        rows = [*self.read_manifest().to_pylist(), row]
        table = pa.Table.from_pylist(rows, schema=MANIFEST_SCHEMA)
        self.root.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.root, suffix=".tmp")
        os.close(fd)
        try:
            pq.write_table(table, tmp)
            os.replace(tmp, self.manifest_path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
