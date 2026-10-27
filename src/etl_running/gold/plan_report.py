"""Informe local de cumplimiento semanal sin exponer GPS ni secretos."""

from __future__ import annotations

from datetime import date

import duckdb

from etl_running.common.config import Settings

STATUS_LABELS = {
    "done": "cumplida",
    "partial": "parcial",
    "missed": "no realizada",
    "upcoming": "próxima",
}
CONFIDENCE_LABELS = {"high": "alta", "medium": "media", "low": "baja", "none": "sin asociación"}
PACE_LABELS = {
    "met": "cumplido",
    "not_met": "no cumplido",
    "not_targeted": "sin objetivo",
    "unverifiable": "sin dato",
}


def _pace(value: float | None) -> str:
    if value is None:
        return "-"
    seconds = round(value)
    return f"{seconds // 60}:{seconds % 60:02d}"


def report_week(settings: Settings, week: date) -> str:
    settings.ensure_in_window(week)
    if week.weekday() != 0:
        raise ValueError("--week debe ser lunes")
    if not settings.warehouse_path.is_file():
        raise FileNotFoundError("Falta Gold: ejecuta `make dbt-build`")
    with duckdb.connect(str(settings.warehouse_path), read_only=True) as con:
        sessions = con.execute(
            """select scheduled_date, title, status, steps_met, targeted_steps,
            confidence, match_method, activity_id, planned_workout_id,
            activity_date, date_offset_days, confirmed_by_user
            from gold.fct_plan_sessions where week_start = ? order by scheduled_date""",
            [week],
        ).fetchall()
        unplanned = con.execute(
            """select activity_date, status from gold.fct_unplanned_runs
            where week_start = ? order by activity_date""",
            [week],
        ).fetchall()
        summary = con.execute(
            """select plan_compliance_pct, verified_steps, targeted_steps
            from gold.fct_weekly_summary
            where week_start = ?""",
            [week],
        ).fetchone()
        lines = [f"Plan vs real · semana {week}"]
        if not sessions:
            lines.append(
                "Sin JSON de plan para esta semana (no_plan); no se inventan sesiones perdidas."
            )
        for (
            day,
            title,
            status,
            met,
            total,
            confidence,
            _method,
            activity_id,
            planned_id,
            actual_day,
            offset,
            confirmed,
        ) in sessions:
            if offset is None:
                shift = "sin carrera asociada"
            elif offset == 0:
                shift = "mismo día"
            else:
                shift = f"desplazado {offset:+d} día{'s' if abs(offset) != 1 else ''}"
            if confirmed:
                shift += " · confirmación manual"
            lines.append(
                f"Plan {day} → carrera {actual_day or '-'} | {title} "
                f"| {STATUS_LABELS.get(status, status)} "
                f"| bloques con ritmo: {met}/{total} | actividad: {activity_id or '-'} "
                f"| {shift} | confianza de sesión: "
                f"{CONFIDENCE_LABELS.get(confidence, confidence)}"
            )
            blocks = con.execute(
                """select kind, repetition, pace_fast_s_km,
                pace_slow_s_km, actual_pace_s_km, pace_status, confidence
                from gold.fct_plan_vs_actual where planned_workout_id = ?
                order by step_seq""",
                [planned_id],
            ).fetchall()
            for kind, rep, fast, slow, actual, block_status, block_conf in blocks:
                if fast is not None:
                    lines.append(
                        f"  {kind}{f' #{rep}' if rep else ''}: "
                        f"obj {_pace(fast)}–{_pace(slow)}, "
                        f"real {_pace(actual)} min/km → "
                        f"{PACE_LABELS.get(block_status, block_status)} "
                        f"({CONFIDENCE_LABELS.get(block_conf, block_conf)})"
                    )
        for day, state in unplanned:
            lines.append(f"{day} | actividad sin sesión asignada: {state}")
        if summary and summary[2]:
            lines.append(f"Bloques verificables: {summary[1]}/{summary[2]}")
        lines.append(
            "Cumplimiento semanal: "
            + (
                f"{summary[0]} %"
                if summary and summary[0] is not None
                else "sin bloques verificables (no implica incumplimiento)"
            )
        )
        return "\n".join(lines)
