"""Definiciones de Dagster para el pipeline local de ETL_Running."""

from __future__ import annotations

from dagster import Definitions

from .assets.alerts import alerts
from .assets.bronze import bronze_activities, bronze_activity_fit
from .assets.silver import (
    silver_activities,
    silver_activity_workout_links,
    silver_fit,
    silver_plan,
)
from .checks import SILVER_CHECKS
from .dbt_assets import dbt_gold
from .jobs import daily_pipeline
from .resources import DBT_RESOURCE, garmin_client_resource, settings_resource
from .schedules import daily_schedule
from .sensors import new_activity_sensor, pipeline_failure_log
from .sources import weekly_plan_source

defs = Definitions(
    assets=[
        bronze_activities,
        silver_activities,
        silver_plan,
        bronze_activity_fit,
        silver_fit,
        silver_activity_workout_links,
        dbt_gold,
        alerts,
        weekly_plan_source,
    ],
    asset_checks=SILVER_CHECKS,
    jobs=[daily_pipeline],
    schedules=[daily_schedule],
    sensors=[new_activity_sensor, pipeline_failure_log],
    resources={
        "settings": settings_resource,
        "garmin_client": garmin_client_resource,
        "dbt": DBT_RESOURCE,
    },
)
