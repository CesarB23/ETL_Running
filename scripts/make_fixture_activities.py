#!/usr/bin/env python3
"""Genera `tests/fixtures/garmin/activities_list.json` (datos 100 % sintéticos).

Imita la forma de `search_activities` de Garmin con 5 actividades:
running normal, running manual, running sin FC, ciclismo y `other`.
Las dos últimas existen solo para probar el filtro de alcance (solo running).
El resultado pasa por el anonimizador, igual que lo haría un export real.

    uv run python scripts/make_fixture_activities.py
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from etl_running.common.anonymize import anonymize

OUTPUT = Path(__file__).resolve().parent.parent / "tests/fixtures/garmin/activities_list.json"
LOCAL_UTC_OFFSET = timedelta(hours=-5)


def _activity(
    activity_id: int,
    start_local: datetime,
    type_key: str,
    type_id: int,
    distance_m: float,
    duration_s: float,
    *,
    avg_hr: float | None = None,
    max_hr: float | None = None,
    cadence: float | None = None,
    gps: bool = True,
    manual: bool = False,
) -> dict:
    start_gmt = start_local - LOCAL_UTC_OFFSET
    speed = distance_m / duration_s if duration_s else 0.0
    return {
        "activityId": activity_id,
        "activityName": "Jane Runner morning run",
        "startTimeLocal": start_local.strftime("%Y-%m-%d %H:%M:%S"),
        "startTimeGMT": start_gmt.strftime("%Y-%m-%d %H:%M:%S"),
        "activityType": {"typeId": type_id, "typeKey": type_key, "parentTypeId": 17},
        "eventType": {"typeId": 9, "typeKey": "uncategorized"},
        "isFavorite": False,
        "isPR": False,
        "isParent": False,
        "distance": distance_m,
        "duration": duration_s,
        "elapsedDuration": duration_s + 12.0,
        "movingDuration": duration_s - 5.0,
        "elevationGain": 42.0 if gps else None,
        "elevationLoss": 40.0 if gps else None,
        "averageSpeed": round(speed, 4),
        "maxSpeed": round(speed * 1.35, 4),
        "startLatitude": 0.0123 if gps else None,
        "startLongitude": 0.0456 if gps else None,
        "ownerId": 123456789,
        "ownerDisplayName": "jane-runner",
        "ownerFullName": "Jane Runner",
        "ownerProfileImageUrlSmall": "https://example.invalid/profile/small.png",
        "ownerProfileImageUrlMedium": "https://example.invalid/profile/medium.png",
        "ownerProfileImageUrlLarge": "https://example.invalid/profile/large.png",
        "calories": round(distance_m * 0.065, 1),
        "averageHR": avg_hr,
        "maxHR": max_hr,
        "averageRunningCadenceInStepsPerMinute": cadence,
        "maxRunningCadenceInStepsPerMinute": cadence + 14.0 if cadence else None,
        "steps": int(duration_s * cadence / 60) if cadence else None,
        "avgStrideLength": 118.0 if cadence else None,
        "lapCount": max(1, round(distance_m / 1000)) if gps and not manual else 1,
        "locationName": "Imaginary Town" if gps else None,
        "manualActivity": manual,
        "manufacturer": None if manual else "GARMIN",
        "moderateIntensityMinutes": round(duration_s / 60) if avg_hr else 0,
        "vigorousIntensityMinutes": 0,
        "beginTimestamp": int(start_gmt.timestamp() * 1000),
        "splitSummaries": [],
    }


def build_raw() -> list[dict]:
    day = datetime(2026, 10, 20, 7, 30)
    return [
        _activity(
            10001, day, "running", 1, 10000.0, 3300.0, avg_hr=148.0, max_hr=171.0, cadence=168.0
        ),
        _activity(
            10002,
            day - timedelta(days=2),
            "running",
            1,
            8000.0,
            2760.0,
            gps=False,
            manual=True,
        ),
        _activity(10003, day - timedelta(days=4), "running", 1, 5000.0, 1620.0, cadence=172.0),
        _activity(
            10004,
            day - timedelta(days=5),
            "cycling",
            2,
            25000.0,
            3600.0,
            avg_hr=132.0,
            max_hr=158.0,
        ),
        _activity(
            10005, day - timedelta(days=6), "other", 3, 0.0, 2400.0, avg_hr=110.0, max_hr=140.0
        ),
    ]


def main() -> int:
    clean = anonymize(build_raw())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(clean, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Escrito {OUTPUT} ({len(clean)} actividades)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
