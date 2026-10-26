"""Carga de configuración desde variables de entorno y `.env`."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

DEFAULT_START_DATE = date(2026, 8, 17)
DEFAULT_RUNNING_TYPE_KEYS = (
    "running",
    "trail_running",
    "treadmill_running",
    "track_running",
)
DEFAULT_LAKE_DIR = "lake"


class ConfigError(ValueError):
    """Configuración inválida."""


class DateOutsideWindowError(ValueError):
    """Se pidió una fecha anterior a `START_DATE`."""


def parse_dotenv(text: str) -> dict[str, str]:
    """Parsea líneas `KEY=VALUE` de un `.env` sin dependencias externas."""
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        values[key] = value.strip().strip("'\"")
    return values


def load_dotenv_values(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    return parse_dotenv(path.read_text(encoding="utf-8"))


def _parse_date(raw: str, name: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} debe tener formato YYYY-MM-DD, recibido: {raw!r}") from exc


def _parse_keys(raw: str) -> tuple[str, ...]:
    keys = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not keys:
        raise ConfigError("RUNNING_TYPE_KEYS no puede estar vacío")
    return keys


@dataclass(frozen=True)
class Settings:
    start_date: date = DEFAULT_START_DATE
    lake_dir: Path = Path(DEFAULT_LAKE_DIR)
    running_type_keys: tuple[str, ...] = DEFAULT_RUNNING_TYPE_KEYS
    api_key: str | None = field(default=None, repr=False)

    @property
    def bronze_dir(self) -> Path:
        return self.lake_dir / "bronze"

    @property
    def silver_dir(self) -> Path:
        return self.lake_dir / "silver"

    @property
    def gold_dir(self) -> Path:
        return self.lake_dir / "gold"

    @property
    def warehouse_path(self) -> Path:
        return self.lake_dir / "warehouse.duckdb"

    def ensure_in_window(self, day: date) -> date:
        """Devuelve `day` o lanza error si es anterior a `start_date`."""
        if day < self.start_date:
            raise DateOutsideWindowError(
                f"{day.isoformat()} es anterior al inicio de la ventana "
                f"({self.start_date.isoformat()})"
            )
        return day

    def secrets(self) -> tuple[str, ...]:
        """Valores que los logs deben redactar."""
        return (self.api_key,) if self.api_key else ()

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        dotenv_path: Path | None = Path(".env"),
    ) -> Settings:
        """Variables de entorno > `.env` > valores por defecto.

        No modifica `os.environ`.
        """
        merged: dict[str, str] = {}
        if dotenv_path is not None:
            merged.update(load_dotenv_values(dotenv_path))
        merged.update(os.environ if env is None else env)

        defaults = cls()
        api_key = merged.get("GARMIN_PERSONAL_API_KEY", "").strip() or None
        return cls(
            start_date=(
                _parse_date(merged["START_DATE"], "START_DATE")
                if merged.get("START_DATE")
                else defaults.start_date
            ),
            lake_dir=Path(merged.get("LAKE_DIR") or DEFAULT_LAKE_DIR),
            running_type_keys=(
                _parse_keys(merged["RUNNING_TYPE_KEYS"])
                if merged.get("RUNNING_TYPE_KEYS")
                else defaults.running_type_keys
            ),
            api_key=api_key,
        )
