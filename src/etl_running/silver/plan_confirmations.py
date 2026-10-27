"""Confirmaciones manuales locales de sesión↔actividad, ligadas al hash del plan."""

from __future__ import annotations

from datetime import UTC, date, datetime

import polars as pl

from etl_running.common.config import Settings
from etl_running.silver.build import _atomic_parquet, activities_path
from etl_running.silver.plan_build import CONFIRMATION_SCHEMA


def confirm_match(settings: Settings, planned_day: date, activity_id: int) -> bool:
    """Registra un vínculo validado por el usuario, sin modificar JSON/ZIP bronze."""
    settings.ensure_in_window(planned_day)
    plans = pl.read_parquet(settings.silver_dir / "planned_workouts.parquet")
    selected = plans.filter(pl.col("scheduled_date") == planned_day)
    if selected.height != 1:
        raise ValueError("Se requiere exactamente una sesión planificada en esa fecha")
    plan = selected.row(0, named=True)
    activities = pl.read_parquet(activities_path(settings.silver_dir))
    selected_activity = activities.filter(pl.col("activity_id") == activity_id)
    if selected_activity.height != 1 or selected_activity["is_manual"].item():
        raise ValueError("La actividad no existe en Silver o es manual")
    activity_day = selected_activity["local_date"].item()
    if abs((activity_day - planned_day).days) > 1:
        raise ValueError("La actividad está fuera de la ventana ±1 día del plan")
    path = settings.silver_dir / "plan_confirmations.parquet"
    existing = pl.read_parquet(path) if path.is_file() else pl.DataFrame(schema=CONFIRMATION_SCHEMA)
    for row in existing.iter_rows(named=True):
        if row["planned_workout_id"] == plan["planned_workout_id"]:
            if row["activity_id"] == activity_id and row["plan_hash"] == plan["plan_hash"]:
                return False
            raise ValueError("Ya hay una confirmación distinta para esa sesión")
        if row["activity_id"] == activity_id:
            raise ValueError("La actividad ya está confirmada para otra sesión")
    new = {
        "planned_workout_id": plan["planned_workout_id"],
        "activity_id": activity_id,
        "plan_hash": plan["plan_hash"],
        "confirmed_at": datetime.now(UTC),
    }
    _atomic_parquet(pl.concat([existing, pl.DataFrame([new], schema=CONFIRMATION_SCHEMA)]), path)
    return True
