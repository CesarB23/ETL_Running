"""Normaliza sesiones JSON del plan; expande repeticiones sin inventar ritmos."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

from etl_running.ingest.plan_loader import PlanError


def _pace(raw: Any) -> tuple[float | None, float | None, float | None, float | None]:
    if raw is None:
        return None, None, None, None
    if (
        not isinstance(raw, list)
        or len(raw) != 2
        or not all(isinstance(value, int | float) and value > 0 for value in raw)
    ):
        raise PlanError("pace_s_km debe ser [rápido, lento]")
    fast, slow = sorted(raw)
    return float(fast), float(slow), 1000.0 / slow, 1000.0 / fast


def parse_week(week: dict, uploads: dict[str, dict] | None = None) -> tuple[list[dict], list[dict]]:
    """`step_order` sigue los órdenes 1-based de week_plan/build.py (sin importar código)."""
    workouts: list[dict] = []
    steps: list[dict] = []
    uploads = uploads or {}
    week_start = date.fromisoformat(week["week_start"])
    for session in week["sessions"]:
        day = date.fromisoformat(session["date"])
        workout_id = f"{week_start}/{day}"
        upload = uploads.get(str(day)) or {}
        garmin_id = upload.get("workoutId")
        plan_hash = hashlib.sha256(
            json.dumps(session, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        workouts.append(
            {
                "planned_workout_id": workout_id,
                "week_start": week_start,
                "scheduled_date": day,
                "title": str(session.get("title") or ""),
                "plan_hash": plan_hash,
                "garmin_workout_id": int(garmin_id) if garmin_id is not None else None,
                "garmin_workout_name": str(upload.get("name")) if upload.get("name") else None,
            }
        )
        order = 1
        sequence = 0

        def add(
            kind: str,
            *,
            step_order: int,
            block: dict,
            repetition: int | None = None,
            distance_m: float | None = None,
            duration_s: float | None = None,
            planned_workout_id: str = workout_id,
        ) -> None:
            nonlocal sequence
            fast, slow, min_mps, max_mps = _pace(block.get("pace_s_km"))
            steps.append(
                {
                    "planned_workout_id": planned_workout_id,
                    "step_seq": sequence,
                    "step_order": step_order,
                    "candidate_fit_index": step_order - 1,
                    "kind": kind,
                    "repetition": repetition,
                    "target_distance_m": distance_m,
                    "target_duration_s": duration_s,
                    "pace_fast_s_km": fast,
                    "pace_slow_s_km": slow,
                    "speed_min_mps": min_mps,
                    "speed_max_mps": max_mps,
                }
            )
            sequence += 1

        for block in session["blocks"]:
            kind = block["kind"]
            if kind == "reps":
                recovery = block.get("recovery")
                for rep in range(int(block["reps"])):
                    add(
                        "work",
                        step_order=order + 1,
                        block=block,
                        repetition=rep + 1,
                        distance_m=block.get("distance_m"),
                        duration_s=block.get("duration_s"),
                    )
                    if recovery and (
                        rep < int(block["reps"]) - 1 or upload.get("include_last_recovery", True)
                    ):
                        add(
                            "recovery",
                            step_order=order + 2,
                            block={},
                            repetition=rep + 1,
                            distance_m=recovery.get("meters"),
                            duration_s=recovery.get("seconds"),
                        )
                order += 3 if recovery else 2
            elif kind in ("warmup", "cooldown", "steady", "jog", "continuous"):
                add(
                    kind,
                    step_order=order,
                    block=block,
                    distance_m=block.get("distance_m"),
                    duration_s=block.get("duration_s"),
                )
                order += 1
            else:
                raise PlanError("Bloque de tipo desconocido")
    return workouts, steps
