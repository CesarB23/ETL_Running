"""Estado por dataset: último `dt` completo, en `lake/_state/cursor.json`."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path


class CursorStore:
    def __init__(self, lake_dir: Path) -> None:
        self.path = lake_dir / "_state" / "cursor.json"

    def _load(self) -> dict[str, dict[str, str]]:
        if not self.path.is_file():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def get(self, dataset_key: str) -> date | None:
        raw = self._load().get(dataset_key, {}).get("last_complete_dt")
        return date.fromisoformat(raw) if raw else None

    def set(self, dataset_key: str, last_complete_dt: date) -> None:
        state = self._load()
        state[dataset_key] = {"last_complete_dt": last_complete_dt.isoformat()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, sort_keys=True)
        os.replace(tmp, self.path)
