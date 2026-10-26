"""FIT con fitdecode: laps, records, sesión y eventos sin interpolar huecos."""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import fitdecode

SEMICIRCLE_TO_DEG = 180 / 2**31


class FitParseError(ValueError):
    """Archivo FIT corrupto o no compatible."""


@dataclass
class FitData:
    laps: list[dict[str, Any]]
    records: list[dict[str, Any]]
    session: dict[str, Any]
    events: list[dict[str, Any]]
    has_workout: bool


def _get(frame: fitdecode.FitDataMessage, key: str) -> Any:
    return frame.get_value(key, fallback=None)


def _utc(value: datetime | None) -> datetime | None:
    return value.astimezone(UTC) if value is not None else None


def _coord(value: int | None) -> float | None:
    return value * SEMICIRCLE_TO_DEG if value is not None else None


def _preferred(frame: fitdecode.FitDataMessage, first: str, second: str) -> Any:
    value = _get(frame, first)
    return value if value is not None else _get(frame, second)


def parse_fit(raw: bytes, activity_id: int) -> FitData:
    laps: list[dict[str, Any]] = []
    records: dict[datetime, dict[str, Any]] = {}
    session: dict[str, Any] = {}
    events: list[dict[str, Any]] = []
    workout = False
    try:
        with fitdecode.FitReader(
            io.BytesIO(raw),
            check_crc=fitdecode.CrcCheck.RAISE,
            error_handling=fitdecode.ErrorHandling.RAISE,
        ) as reader:
            for frame in reader:
                if not isinstance(frame, fitdecode.FitDataMessage):
                    continue
                if frame.name in ("workout", "workout_step"):
                    workout = True
                if frame.name == "session":
                    session = {
                        "distance_m": _get(frame, "total_distance"),
                        "duration_s": _get(frame, "total_timer_time"),
                    }
                elif frame.name == "lap":
                    laps.append(
                        {
                            "activity_id": activity_id,
                            "lap_index": len(laps),
                            "start_utc": _utc(_get(frame, "start_time")),
                            "end_utc": _utc(_get(frame, "timestamp")),
                            "distance_m": _get(frame, "total_distance"),
                            "duration_s": _get(frame, "total_timer_time"),
                            "elapsed_s": _get(frame, "total_elapsed_time"),
                            "avg_speed_mps": _preferred(frame, "enhanced_avg_speed", "avg_speed"),
                            "avg_hr": _get(frame, "avg_heart_rate"),
                            "max_hr": _get(frame, "max_heart_rate"),
                            "avg_cadence_spm": _get(frame, "avg_running_cadence"),
                            "elev_gain_m": _get(frame, "total_ascent"),
                            "lap_trigger": _get(frame, "lap_trigger"),
                            "intensity": _get(frame, "intensity"),
                            "wkt_step_index": _get(frame, "wkt_step_index"),
                        }
                    )
                elif frame.name == "record":
                    ts = _utc(_get(frame, "timestamp"))
                    if ts is None:
                        continue
                    # Duplicados por segundo: última lectura gana, conservando huecos.
                    records[ts] = {
                        "activity_id": activity_id,
                        "ts_utc": ts,
                        "distance_m": _get(frame, "distance"),
                        "speed_mps": _preferred(frame, "enhanced_speed", "speed"),
                        "heart_rate": _get(frame, "heart_rate"),
                        "cadence_spm": _get(frame, "cadence"),
                        "altitude_m": _preferred(frame, "enhanced_altitude", "altitude"),
                        "lat": _coord(_get(frame, "position_lat")),
                        "lon": _coord(_get(frame, "position_long")),
                    }
                elif frame.name == "event" and _get(frame, "event") == "timer":
                    events.append(
                        {
                            "ts_utc": _utc(_get(frame, "timestamp")),
                            "event_type": _get(frame, "event_type"),
                        }
                    )
    except (fitdecode.FitError, OSError, ValueError) as exc:
        raise FitParseError("FIT corrupto o ilegible") from exc
    if not laps and not records:
        raise FitParseError("FIT sin laps ni records")
    ordered_records = list(sorted(records.values(), key=lambda row: row["ts_utc"]))
    timer_events = sorted(
        (event for event in events if event["ts_utc"] is not None),
        key=lambda event: event["ts_utc"],
    )
    event_index = 0
    timer_running = True
    for record in ordered_records:
        while (
            event_index < len(timer_events)
            and timer_events[event_index]["ts_utc"] <= record["ts_utc"]
        ):
            kind = timer_events[event_index]["event_type"]
            if kind in ("stop", "stop_all", "stop_disable", "stop_disable_all"):
                timer_running = False
            elif kind == "start":
                timer_running = True
            event_index += 1
        record["timer_running"] = timer_running
    return FitData(laps, ordered_records, session, events, workout)
