"""Recursos, particiones y preparación del proyecto dbt para Dagster."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from dagster import DailyPartitionsDefinition, resource
from dagster_dbt import DbtCliResource, DbtProject

from etl_running.common.config import Settings
from etl_running.ingest.garmin_client import ResilientClient, open_client

ROOT = Path(__file__).resolve().parents[1]
DBT_DIR = ROOT / "dbt"
TIMEZONE = "America/Mexico_City"


def _bootstrap_settings() -> Settings:
    """Carga la configuración y exporta lo que dbt necesita en sus perfiles.

    `Settings` no modifica el entorno por diseño. Dagster sí necesita que dbt vea
    exactamente el mismo `LAKE_DIR` y `START_DATE`, y además en absoluto: dbt se
    ejecuta con el directorio del proyecto como cwd, así que un `lake` relativo
    apuntaría a `dbt/lake`.
    """
    settings = Settings.from_env()
    os.environ["LAKE_DIR"] = str(settings.lake_dir.resolve())
    os.environ.setdefault("START_DATE", settings.start_date.isoformat())
    return settings


BOOTSTRAP_SETTINGS = _bootstrap_settings()

# Una partición por día para la ingesta. El schedule diario usa esta definición;
# el job no particionado (`daily_pipeline`) mantiene el comando sencillo de CLI.
DAILY_PARTITIONS = DailyPartitionsDefinition(
    start_date=BOOTSTRAP_SETTINGS.start_date.isoformat(),
    timezone=TIMEZONE,
    # A las 20:00 de CDMX el día aún no termina; incluirlo para que el schedule
    # ingiera la fecha actual, no la última partición ya cerrada.
    end_offset=1,
)

DBT_PROJECT = DbtProject(
    project_dir=DBT_DIR,
    profiles_dir=DBT_DIR,
    target_path=DBT_DIR / "target",
)


def dbt_manifest_path() -> Path:
    """Devuelve el manifest de dbt, generándolo si el checkout está limpio."""
    if not DBT_PROJECT.manifest_path.is_file():
        DBT_PROJECT.preparer.prepare(DBT_PROJECT)
    return DBT_PROJECT.manifest_path


DBT_RESOURCE = DbtCliResource(project_dir=DBT_PROJECT)


def plan_uploads_path() -> Path:
    """JSON local de subidas (workoutId); opcional y nunca versionado."""
    raw = os.environ.get("GARMIN_UPLOADS_JSON")
    return Path(raw) if raw else ROOT.parent / "Garmin" / "data" / "uploads.json"


@resource
def settings_resource() -> Settings:
    """Relee `.env` en cada run para no fijar secretos al importar."""
    return Settings.from_env()


@resource(required_resource_keys={"settings"})
def garmin_client_resource(context: Any) -> Iterator[ResilientClient]:
    """Cliente real con reintentos de red; en tests se sustituye por un fake."""
    with open_client(context.resources.settings) as client:
        yield client
