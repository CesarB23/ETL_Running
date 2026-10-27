"""Carga planes semanales ya parseados a bronze, sin tocar el PDF ni ../Garmin/."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from etl_running.bronze.writer import BronzeWriter, new_run_id
from etl_running.common.config import Settings


class PlanError(ValueError):
    """Plan semanal inválido."""


def validate_week(payload: Any, settings: Settings) -> date:
    if not isinstance(payload, dict) or not isinstance(payload.get("sessions"), list):
        raise PlanError("Se espera un objeto con lista de sesiones")
    try:
        week = date.fromisoformat(payload["week_start"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PlanError("week_start debe ser YYYY-MM-DD") from exc
    settings.ensure_in_window(week)
    if week.weekday() != 0:
        raise PlanError("week_start debe ser lunes")
    days = set()
    for session in payload["sessions"]:
        if not isinstance(session, dict) or not isinstance(session.get("blocks"), list):
            raise PlanError("Sesión sin bloques")
        try:
            day = date.fromisoformat(session["date"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PlanError("Sesión sin fecha válida") from exc
        if day < week or (day - week).days > 6 or day in days:
            raise PlanError("Sesión fuera de semana o fecha duplicada")
        days.add(day)
    return week


def load_week(settings: Settings, path: Path) -> bool:
    """Carga el documento original como lista de un elemento, versionado por hash."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    week = validate_week(payload, settings)
    return (
        BronzeWriter(settings.bronze_dir)
        .write_partition("plan", "weekly_plan", week, [payload], new_run_id())
        .written
    )
