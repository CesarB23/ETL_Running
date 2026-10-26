"""Payload de `search_activities` (Garmin) → fila de `silver.activities`."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

PARSER_VERSION = "2"
HR_MIN, HR_MAX = 30, 230
TREADMILL_KEYS = frozenset({"treadmill_running"})


class ParseError(ValueError):
    """El registro no se puede convertir en una fila válida."""


@dataclass
class ParsedActivity:
    row: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


def _num(raw: dict[str, Any], key: str) -> float | None:
    """Número o `None` si falta. Nunca convierte ausencia en 0."""
    value = raw.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ParseError(f"{key} no es numérico")
    value = float(value)
    if not math.isfinite(value):
        raise ParseError(f"{key} no es finito")
    return value


def _int(raw: dict[str, Any], key: str) -> int | None:
    value = _num(raw, key)
    if value is not None and not value.is_integer():
        raise ParseError(f"{key} no es entero")
    return None if value is None else int(value)


def _timestamp(raw: dict[str, Any], key: str) -> datetime:
    value = raw.get(key)
    if not isinstance(value, str):
        raise ParseError(f"{key} ausente o no es texto")
    try:
        return datetime.fromisoformat(value.replace(" ", "T"))
    except ValueError as exc:
        raise ParseError(f"{key} con formato inválido") from exc


def _offset(local: datetime, gmt: datetime) -> tuple[int, str]:
    """Desfase local−GMT en minutos y su texto `±HH:MM` (cambia con el DST)."""
    minutes = round((local - gmt) / timedelta(minutes=1))
    if abs(minutes) > 14 * 60 or minutes % 15:
        raise ParseError(f"desfase local/GMT imposible: {minutes} min")
    sign = "-" if minutes < 0 else "+"
    hours, mins = divmod(abs(minutes), 60)
    return minutes, f"{sign}{hours:02d}:{mins:02d}"


def _heart_rate(raw: dict[str, Any], key: str, warnings: list[str]) -> float | None:
    value = _num(raw, key)
    if value is None:
        return None
    if HR_MIN <= value <= HR_MAX:
        return value
    warnings.append(f"{key}={value:g} fuera de {HR_MIN}–{HR_MAX}: se guarda NULL")
    return None


def parse_activity(raw: dict[str, Any]) -> ParsedActivity:
    warnings: list[str] = []

    activity_id = raw.get("activityId")
    if isinstance(activity_id, bool) or not isinstance(activity_id, int):
        raise ParseError("activityId ausente o no entero")
    activity_type = raw.get("activityType")
    type_key = activity_type.get("typeKey") if isinstance(activity_type, dict) else None
    if not isinstance(type_key, str) or not type_key:
        raise ParseError("activityType.typeKey ausente")

    local = _timestamp(raw, "startTimeLocal")
    gmt = _timestamp(raw, "startTimeGMT")
    offset_min, tz_local = _offset(local, gmt)

    lat, lon = _num(raw, "startLatitude"), _num(raw, "startLongitude")
    has_gps = (
        type_key not in TREADMILL_KEYS
        and lat is not None
        and lon is not None
        and (lat, lon) != (0, 0)
    )
    stride_cm = _num(raw, "avgStrideLength")

    row = {
        "activity_id": activity_id,
        "activity_type": type_key,
        "is_manual": bool(raw.get("manualActivity") or raw.get("isManualActivity")),
        "has_gps": has_gps,
        "start_utc": gmt.replace(tzinfo=UTC),
        "start_local": local,
        "local_date": local.date(),
        "tz_local": tz_local,
        "utc_offset_min": offset_min,
        "distance_m": _num(raw, "distance"),
        "duration_s": _num(raw, "duration"),
        "moving_s": _num(raw, "movingDuration"),
        "elapsed_s": _num(raw, "elapsedDuration"),
        "avg_speed_mps": _num(raw, "averageSpeed"),
        "max_speed_mps": _num(raw, "maxSpeed"),
        "avg_hr": _heart_rate(raw, "averageHR", warnings),
        "max_hr": _heart_rate(raw, "maxHR", warnings),
        "avg_cadence_spm": _num(raw, "averageRunningCadenceInStepsPerMinute"),
        "stride_m": None if stride_cm is None else stride_cm / 100,
        "elev_gain_m": _num(raw, "elevationGain"),
        "elev_loss_m": _num(raw, "elevationLoss"),
        "calories": _num(raw, "calories"),
        "lap_count": _int(raw, "lapCount"),
        "moderate_intensity_min": _int(raw, "moderateIntensityMinutes"),
        "vigorous_intensity_min": _int(raw, "vigorousIntensityMinutes"),
        "start_lat": lat if has_gps else None,
        "start_lon": lon if has_gps else None,
    }
    return ParsedActivity(row, warnings)
