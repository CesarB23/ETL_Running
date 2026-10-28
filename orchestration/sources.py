"""Fuentes externas que no materializa el pipeline diario."""

from __future__ import annotations

from dagster import AssetKey, SourceAsset

# El plan semanal se carga con `etl_running plan load`; no se descarga de Garmin.
WEEKLY_PLAN = AssetKey(["bronze", "weekly_plan"])

weekly_plan_source = SourceAsset(
    key=WEEKLY_PLAN,
    description="JSON semanal cargado manualmente en bronze con `plan load`.",
)
