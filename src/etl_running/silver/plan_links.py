"""Enlaza actividades con workouts de Garmin SOLO con nombre API exacto y fecha próxima."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import polars as pl

from etl_running.common.config import Settings
from etl_running.silver.build import _atomic_json, _atomic_parquet, activities_path
from etl_running.silver.plan_build import LINK_SCHEMA

LOGGER = logging.getLogger("etl_running.silver.plan_links")


def collect_links(settings: Settings, client: Any, *, refresh: bool = False) -> int:
    """Nunca inventa workoutId: empareja nombre API con upload registrado en JSON local."""
    workouts_path = settings.silver_dir / "planned_workouts.parquet"
    activities_file = activities_path(settings.silver_dir)
    plans = pl.read_parquet(workouts_path).to_dicts()
    activities = pl.read_parquet(activities_file).to_dicts()
    fingerprint = hashlib.sha256(
        workouts_path.read_bytes() + activities_file.read_bytes()
    ).hexdigest()
    state_path = settings.silver_dir / "_workout_links.json"
    if not refresh and state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("fingerprint") == fingerprint:
            LOGGER.info("Asociaciones de workout sin cambios")
            return state["count"]
    candidates: dict[int, list[dict]] = {}
    for activity in activities:
        if activity["is_manual"]:
            continue
        nearby = [
            plan
            for plan in plans
            if plan["garmin_workout_id"] is not None
            and plan["garmin_workout_name"]
            and abs((activity["local_date"] - plan["scheduled_date"]).days) <= 1
        ]
        if nearby:
            candidates[activity["activity_id"]] = nearby
    links: list[dict] = []
    used_plans: set[str] = set()
    for activity_id, nearby in candidates.items():
        response = client.get_activity_workouts(activity_id)
        names = (
            {
                str(item.get("workoutName", "")).strip().casefold()
                for item in response
                if isinstance(item, dict)
            }
            if isinstance(response, list)
            else set()
        )
        matched = [
            plan for plan in nearby if plan["garmin_workout_name"].strip().casefold() in names
        ]
        if len(matched) == 1 and matched[0]["planned_workout_id"] not in used_plans:
            plan = matched[0]
            links.append(
                {
                    "activity_id": activity_id,
                    "planned_workout_id": plan["planned_workout_id"],
                    "garmin_workout_id": plan["garmin_workout_id"],
                    "match_method": "workout_name",
                }
            )
            used_plans.add(plan["planned_workout_id"])
    _atomic_parquet(
        pl.DataFrame(links, schema=LINK_SCHEMA),
        settings.silver_dir / "activity_workout_links.parquet",
    )
    _atomic_json({"fingerprint": fingerprint, "count": len(links)}, state_path)
    LOGGER.info("Asociaciones confirmadas por nombre de workout API: %d", len(links))
    return len(links)
