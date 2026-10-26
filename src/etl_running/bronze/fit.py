"""ZIP FIT original en bronze; archivo inmutable y manifestado por actividad."""

from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

from etl_running.bronze.writer import BronzeWriter, new_run_id


class FitArchiveError(ValueError):
    """La descarga no contiene exactamente un FIT válido en un ZIP."""


def fit_bytes(data: bytes) -> bytes:
    """Extrae en memoria sin escribir rutas provistas por el ZIP."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = [
                item
                for item in archive.infolist()
                if item.filename.lower().endswith(".fit") and not item.is_dir()
            ]
            if len(members) != 1 or members[0].file_size > 50_000_000:
                raise FitArchiveError("ZIP sin un único FIT válido (máximo 50 MB)")
            result = archive.read(members[0])
    except (zipfile.BadZipFile, RuntimeError, EOFError) as exc:
        raise FitArchiveError("ZIP corrupto") from exc
    if len(result) < 12 or result[8:12] != b".FIT":
        raise FitArchiveError("El contenido no es un FIT")
    return result


class FitWriter:
    def __init__(self, bronze_dir: Path):
        self.writer = BronzeWriter(bronze_dir)

    def present_ids(self) -> set[int]:
        return {
            int(Path(row["path"]).stem)
            for row in self.writer.read_manifest().to_pylist()
            if row["source"] == "garmin" and row["dataset"] == "activity_fit"
        }

    def write(self, activity_id: int, dt: date, data: bytes) -> bool:
        """Valida antes de escribir; si existe no modifica ZIP ni manifiesto."""
        fit_bytes(data)
        if activity_id in self.present_ids():
            return False
        run_id = new_run_id()
        target = self.writer.root / "garmin" / "activity_fit" / f"dt={dt}" / f"{activity_id}.zip"
        if target.exists():
            raise FileExistsError(
                "FIT ya existe sin registro en el manifiesto; revisar manualmente"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        self.writer._atomic_write(target, data)
        self.writer._append_manifest(
            {
                "source": "garmin",
                "dataset": "activity_fit",
                "dt": dt,
                "run_id": run_id,
                "path": str(target.relative_to(self.writer.root)),
                "sha256": hashlib.sha256(data).hexdigest(),
                "n_records": 1,
                "n_bytes": len(data),
                "ingested_at": datetime.now(UTC),
            }
        )
        return True
