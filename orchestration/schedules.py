"""Schedule diario del pipeline."""

from __future__ import annotations

from dagster import DefaultScheduleStatus, build_schedule_from_partitioned_job

from .jobs import daily_pipeline

daily_schedule = build_schedule_from_partitioned_job(
    daily_pipeline,
    name="daily_pipeline_schedule",
    description="Ejecuta el pipeline completo cada día a las 20:00 (America/Mexico_City).",
    hour_of_day=20,
    minute_of_hour=0,
    default_status=DefaultScheduleStatus.RUNNING,
)
