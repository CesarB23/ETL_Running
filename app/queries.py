"""Consultas de solo lectura para el dashboard; toda la lógica vive en Gold."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from etl_running.common.config import Settings

DEMO_ENV = "DEMO_MODE"
DEMO_LAKE_ENV = "DEMO_LAKE_DIR"
DEFAULT_DEMO_LAKE = Path("lake_demo")


class DashboardError(RuntimeError):
    """Falta el warehouse o una tabla necesaria para el dashboard."""


def demo_mode() -> bool:
    return os.getenv(DEMO_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def warehouse_path(path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path)
    if demo_mode():
        return Path(os.getenv(DEMO_LAKE_ENV) or DEFAULT_DEMO_LAKE) / "warehouse.duckdb"
    return Settings.from_env().warehouse_path


def _connect(path: Path | str | None = None) -> duckdb.DuckDBPyConnection:
    target = warehouse_path(path)
    if not target.is_file():
        raise DashboardError(
            f"No existe el warehouse {target}. "
            "Ejecuta `make dbt-build` o `make demo` para el modo sintético."
        )
    return duckdb.connect(str(target), read_only=True)


def _frame(
    sql: str, params: list[Any] | None = None, path: Path | str | None = None
) -> pd.DataFrame:
    with _connect(path) as con:
        try:
            return con.execute(sql, params or []).df()
        except duckdb.Error as exc:
            raise DashboardError(f"No se pudo consultar Gold: {exc}") from exc


def latest_snapshot(path: Path | str | None = None) -> dict[str, Any]:
    """KPIs de la cabecera, calculados con datos ya agregados en Gold."""
    with _connect(path) as con:
        try:
            row = con.execute(
                """
                select
                    (select max(activity_date) from gold.fct_runs) as last_run_date,
                    (select count(*) from gold.fct_runs
                     where not is_manual
                       and activity_date >= current_date - interval 7 day) as runs_7d,
                    (select coalesce(sum(distance_m), 0) / 1000.0 from gold.fct_runs
                     where not is_manual
                       and activity_date >= current_date - interval 7 day) as km_7d,
                    (select coalesce(sum(duration_s), 0) / 3600.0 from gold.fct_runs
                     where not is_manual
                       and activity_date >= current_date - interval 7 day) as hours_7d,
                    (select acwr from gold.fct_training_load
                     where is_reliable order by activity_date desc limit 1) as acwr,
                    (select is_reliable from gold.fct_training_load
                     order by activity_date desc limit 1) as acwr_reliable,
                    (select plan_compliance_pct from gold.fct_weekly_summary
                     where plan_compliance_pct is not null
                     order by week_start desc limit 1) as plan_compliance_pct
                """
            ).fetchone()
        except duckdb.Error as exc:
            raise DashboardError(f"No se pudo consultar Gold: {exc}") from exc
    keys = (
        "last_run_date",
        "runs_7d",
        "km_7d",
        "hours_7d",
        "acwr",
        "acwr_reliable",
        "plan_compliance_pct",
    )
    return dict(zip(keys, row, strict=True))


def weekly_summary(path: Path | str | None = None) -> pd.DataFrame:
    return _frame(
        """
        select week_start, run_count, distance_km, duration_s,
               elev_gain_m, plan_compliance_pct
        from gold.fct_weekly_summary
        order by week_start
        """,
        path=path,
    )


def recent_runs(limit: int = 12, path: Path | str | None = None) -> pd.DataFrame:
    return _frame(
        """
        select activity_date, activity_type, round(distance_m / 1000.0, 2) as km,
               round(duration_s / 60.0, 1) as minutes, round(pace_min_km, 2) as pace_min_km,
               round(avg_hr, 0) as avg_hr, round(aerobic_efficiency, 4) as aerobic_efficiency
        from gold.fct_runs
        where not is_manual
        order by activity_date desc
        limit ?
        """,
        [limit],
        path,
    )


def progress(days: int = 120, path: Path | str | None = None) -> pd.DataFrame:
    return _frame(
        """
        select activity_date, pace_min_km, aerobic_efficiency, cardiac_drift_pct, avg_hr
        from gold.fct_runs
        where is_valid_for_pace and not is_manual
          and activity_date >= current_date - cast(? as integer) * interval 1 day
        order by activity_date
        """,
        [days],
        path,
    )


def training_load(days: int = 120, path: Path | str | None = None) -> pd.DataFrame:
    return _frame(
        """
        select activity_date, training_load, acute_7d, chronic_28d, acwr, is_reliable
        from gold.fct_training_load
        where activity_date >= current_date - cast(? as integer) * interval 1 day
        order by activity_date
        """,
        [days],
        path,
    )


def plan_weeks(path: Path | str | None = None) -> list:
    frame = _frame(
        "select distinct week_start from gold.fct_plan_sessions order by week_start desc",
        path=path,
    )
    return [value.date() if hasattr(value, "date") else value for value in frame["week_start"]]


def plan_sessions(week_start, path: Path | str | None = None) -> pd.DataFrame:
    return _frame(
        """
        select planned_workout_id, scheduled_date, title, status, activity_id, activity_date,
               date_offset_days, confirmed_by_user, confidence, match_method,
               targeted_steps, steps_met, verified_steps, steps_unverifiable
        from gold.fct_plan_sessions
        where week_start = ?
        order by scheduled_date
        """,
        [week_start],
        path,
    )


def plan_week_summary(week_start, path: Path | str | None = None) -> dict[str, Any]:
    frame = _frame(
        """
        select plan_compliance_pct, targeted_steps, steps_met, verified_steps
        from gold.fct_weekly_summary
        where week_start = ?
        """,
        [week_start],
        path,
    )
    if frame.empty:
        return {
            "plan_compliance_pct": None,
            "targeted_steps": 0,
            "steps_met": 0,
            "verified_steps": 0,
        }
    row = frame.iloc[0]
    return {
        "plan_compliance_pct": None
        if pd.isna(row["plan_compliance_pct"])
        else float(row["plan_compliance_pct"]),
        "targeted_steps": int(row["targeted_steps"]) if pd.notna(row["targeted_steps"]) else 0,
        "steps_met": int(row["steps_met"]) if pd.notna(row["steps_met"]) else 0,
        "verified_steps": int(row["verified_steps"]) if pd.notna(row["verified_steps"]) else 0,
    }


def plan_blocks(week_start, path: Path | str | None = None) -> pd.DataFrame:
    return _frame(
        """
        select planned_workout_id, scheduled_date, kind, repetition,
               target_distance_m,
               round(pace_fast_s_km, 0) as pace_fast_s_km,
               round(pace_slow_s_km, 0) as pace_slow_s_km,
               round(actual_pace_s_km, 0) as actual_pace_s_km,
               round(deviation_s_km, 0) as deviation_s_km,
               pace_status, confidence
        from gold.fct_plan_vs_actual
        where week_start = ?
        order by scheduled_date, step_seq
        """,
        [week_start],
        path,
    )


def data_quality(path: Path | str | None = None) -> pd.DataFrame:
    return _frame(
        """
        select dataset, row_count, distinct_keys, max_activity_date, rejected_count
        from gold.mart_data_quality
        order by dataset
        """,
        path=path,
    )


def alerts_tail(limit: int = 15, path: Path | str | None = None) -> list[str]:
    """Últimas líneas del log local; no se muestra nada si no existe."""
    target = Path(path) if path is not None else warehouse_path().parent / "alerts.log"
    if not target.is_file():
        return []
    return target.read_text(encoding="utf-8").splitlines()[-limit:]
