"""Genera un warehouse Gold sintético para el modo demo del dashboard."""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta
from pathlib import Path

import duckdb

DEMO_WEEKS = 12

SCHEMA = {
    "fct_runs": """
        activity_id BIGINT PRIMARY KEY,
        activity_date DATE,
        start_utc TIMESTAMP,
        activity_type VARCHAR,
        is_manual BOOLEAN,
        has_gps BOOLEAN,
        distance_m DOUBLE,
        duration_s DOUBLE,
        avg_speed_mps DOUBLE,
        avg_hr DOUBLE,
        avg_cadence_spm DOUBLE,
        elev_gain_m DOUBLE,
        elev_loss_m DOUBLE,
        moderate_intensity_min DOUBLE,
        vigorous_intensity_min DOUBLE,
        pace_min_km DOUBLE,
        aerobic_efficiency DOUBLE,
        cardiac_drift_pct DOUBLE,
        is_valid_for_pace BOOLEAN
    """,
    "fct_training_load": """
        activity_date DATE PRIMARY KEY,
        training_load DOUBLE,
        acute_7d DOUBLE,
        chronic_28d DOUBLE,
        acwr DOUBLE,
        is_reliable BOOLEAN
    """,
    "fct_weekly_summary": """
        week_start DATE PRIMARY KEY,
        run_count BIGINT,
        distance_m DOUBLE,
        duration_s DOUBLE,
        elev_gain_m DOUBLE,
        distance_km DOUBLE,
        targeted_steps BIGINT,
        steps_met BIGINT,
        verified_steps BIGINT,
        plan_compliance_pct DOUBLE
    """,
    "fct_plan_sessions": """
        planned_workout_id VARCHAR PRIMARY KEY,
        week_start DATE,
        scheduled_date DATE,
        title VARCHAR,
        garmin_workout_id BIGINT,
        plan_hash VARCHAR,
        activity_id BIGINT,
        activity_date DATE,
        date_offset_days INTEGER,
        confirmed_by_user BOOLEAN,
        match_method VARCHAR,
        confidence VARCHAR,
        targeted_steps BIGINT,
        steps_met BIGINT,
        verified_steps BIGINT,
        steps_unverifiable BIGINT,
        indexed_steps BIGINT,
        status VARCHAR
    """,
    "fct_plan_vs_actual": """
        planned_step_id VARCHAR PRIMARY KEY,
        planned_workout_id VARCHAR,
        step_seq INTEGER,
        step_order INTEGER,
        kind VARCHAR,
        repetition INTEGER,
        scheduled_date DATE,
        week_start DATE,
        activity_id BIGINT,
        target_distance_m DOUBLE,
        target_duration_s DOUBLE,
        pace_fast_s_km DOUBLE,
        pace_slow_s_km DOUBLE,
        speed_min_mps DOUBLE,
        speed_max_mps DOUBLE,
        matched_lap_index INTEGER,
        matched_island_lap INTEGER,
        match_method VARCHAR,
        confidence VARCHAR,
        actual_pace_s_km DOUBLE,
        deviation_s_km DOUBLE,
        pace_status VARCHAR
    """,
    "mart_data_quality": """
        dataset VARCHAR PRIMARY KEY,
        row_count BIGINT,
        distinct_keys BIGINT,
        max_activity_date DATE,
        rejected_count BIGINT
    """,
}


def _insert(con: duckdb.DuckDBPyConnection, table: str, rows: list[tuple]) -> None:
    if not rows:
        return
    marks = ", ".join("?" for _ in rows[0])
    con.executemany(f"insert into gold.{table} values ({marks})", rows)


def _runs_for_week(rng: random.Random, week_start: date, week_index: int) -> list[dict]:
    """Tres o cuatro carreras con progresión suave y sin datos personales."""
    pattern = [
        (1, "series", 8.0, 5.35),
        (3, "easy", 7.0, 6.15),
        (6, "long", 12.0 + (week_index % 3), 6.05),
    ]
    if rng.random() < 0.35:
        pattern.append((5, "easy", 5.0, 6.40))

    runs = []
    for offset, kind, base_km, base_pace in pattern:
        day = week_start + timedelta(days=offset)
        if day > date.today():
            continue
        km = round(base_km + rng.uniform(-0.8, 0.8), 2)
        pace = round(base_pace - week_index * 0.012 + rng.uniform(-0.12, 0.12), 2)
        pace = max(4.9, min(7.0, pace))
        duration_s = round(pace * 60 * km, 1)
        speed = km * 1000 / duration_s
        hr = round((150 if kind == "series" else 143) + rng.uniform(-5, 5), 1)
        runs.append(
            {
                "kind": kind,
                "activity_date": day,
                "start_utc": datetime.combine(day, time(7, 30)),
                "distance_m": round(km * 1000, 1),
                "duration_s": duration_s,
                "avg_speed_mps": speed,
                "avg_hr": hr,
                "avg_cadence_spm": round(171 + rng.uniform(-4, 4), 1),
                "elev_gain_m": round(rng.uniform(15, 90), 1),
                "elev_loss_m": round(rng.uniform(15, 90), 1),
                "moderate_intensity_min": round(duration_s / 60 * 0.62, 1),
                "vigorous_intensity_min": round(
                    duration_s / 60 * (0.22 if kind == "series" else 0.08), 1
                ),
                "pace_min_km": pace,
                "aerobic_efficiency": speed / hr,
                "cardiac_drift_pct": round(rng.uniform(-2.5, 4.5), 2),
            }
        )
    return runs


def _plan_rows(runs_by_day: dict[date, dict], today: date) -> tuple[list[tuple], list[tuple]]:
    sessions: list[tuple] = []
    blocks: list[tuple] = []
    plan_days = {1: "Series", 3: "Rodaje suave", 6: "Tirada larga"}
    first_plan_week = today - timedelta(weeks=5)
    first_plan_week -= timedelta(days=first_plan_week.weekday())

    week_start = first_plan_week
    while week_start <= today:
        for offset, title in plan_days.items():
            scheduled = week_start + timedelta(days=offset)
            workout_id = f"demo-{scheduled.isoformat()}"
            candidates = [
                runs_by_day.get(scheduled + timedelta(days=shift)) for shift in (0, 1, -1)
            ]
            run = next((item for item in candidates if item is not None), None)
            activity_date = run["activity_date"] if run else None
            activity_id = run.get("activity_id") if run else None
            offset_days = (activity_date - scheduled).days if activity_date else None

            steps = [
                ("warmup", 1, None, None, None, None),
                ("interval", 2, 5000.0, 315.0, 325.0, 1),
                ("recovery", 3, None, None, None, None),
                ("cooldown", 4, None, None, None, None),
            ]
            targeted = 0
            met = 0
            verified = 0
            unverifiable = 0
            for seq, (kind, order, target_m, fast, slow, repetition) in enumerate(steps, start=1):
                if fast is not None:
                    targeted += 1
                    actual = round(run["pace_min_km"] * 60, 1) if run else None
                    if actual is None:
                        status = "unverifiable"
                        unverifiable += 1
                        method = "none"
                        confidence = "none"
                    else:
                        verified += 1
                        status = "met" if fast - 5 <= actual <= slow + 5 else "not_met"
                        met += status == "met"
                        method = "wkt_step"
                        confidence = "high"
                    deviation = round(actual - (fast + slow) / 2, 1) if actual else None
                else:
                    actual = round(run["pace_min_km"] * 60, 1) if run else None
                    status = "not_targeted"
                    method = "none"
                    confidence = "none"
                    deviation = None
                blocks.append(
                    (
                        f"{workout_id}-{seq}",
                        workout_id,
                        seq,
                        order,
                        kind,
                        repetition or 1,
                        scheduled,
                        week_start,
                        activity_id,
                        target_m,
                        None,
                        fast,
                        slow,
                        1000 / slow if slow else None,
                        1000 / fast if fast else None,
                        1 if run and fast is not None else None,
                        None,
                        method,
                        confidence,
                        actual,
                        deviation,
                        status,
                    )
                )

            if activity_id is None:
                status = "upcoming" if scheduled >= today else "missed"
            elif targeted == 0 or met == targeted:
                status = "done"
            else:
                status = "partial"

            sessions.append(
                (
                    workout_id,
                    week_start,
                    scheduled,
                    title,
                    None,
                    "demo-plan-v1",
                    activity_id,
                    activity_date,
                    offset_days,
                    False,
                    "wkt_step" if activity_id else "none",
                    "high" if activity_id else "none",
                    targeted,
                    met,
                    verified,
                    unverifiable,
                    targeted if activity_id else 0,
                    status,
                )
            )
        week_start += timedelta(days=7)
    return sessions, blocks


def build_demo_warehouse(path: Path | str, *, seed: int = 42, weeks: int = DEMO_WEEKS) -> Path:
    """Crea un DuckDB Gold determinista con datos ficticios de running."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()

    rng = random.Random(seed)
    today = date.today()
    start = today - timedelta(weeks=weeks - 1)
    start -= timedelta(days=start.weekday())

    runs: list[dict] = []
    for week_index in range(weeks):
        week_start = start + timedelta(weeks=week_index)
        for run in _runs_for_week(rng, week_start, week_index):
            run["activity_id"] = 900000 + len(runs)
            run["activity_type"] = "running"
            run["is_manual"] = False
            run["has_gps"] = True
            run["is_valid_for_pace"] = True
            runs.append(run)
    runs_by_day = {run["activity_date"]: run for run in runs}

    run_rows = [
        (
            r["activity_id"],
            r["activity_date"],
            r["start_utc"],
            r["activity_type"],
            r["is_manual"],
            r["has_gps"],
            r["distance_m"],
            r["duration_s"],
            r["avg_speed_mps"],
            r["avg_hr"],
            r["avg_cadence_spm"],
            r["elev_gain_m"],
            r["elev_loss_m"],
            r["moderate_intensity_min"],
            r["vigorous_intensity_min"],
            r["pace_min_km"],
            r["aerobic_efficiency"],
            r["cardiac_drift_pct"],
            r["is_valid_for_pace"],
        )
        for r in runs
    ]

    daily_load: dict[date, float] = {}
    for r in runs:
        daily_load[r["activity_date"]] = daily_load.get(r["activity_date"], 0.0) + (
            r["moderate_intensity_min"] + 2 * r["vigorous_intensity_min"]
        )

    load_rows = []
    day = start
    load_by_day = []
    while day <= today:
        load_by_day.append(daily_load.get(day, 0.0))
        day += timedelta(days=1)
    for index, day in enumerate([start + timedelta(days=i) for i in range(len(load_by_day))]):
        acute = sum(load_by_day[max(0, index - 6) : index + 1]) / min(7, index + 1)
        chronic = sum(load_by_day[max(0, index - 27) : index + 1]) / min(28, index + 1)
        reliable = index + 1 >= 28 and chronic > 0
        load_rows.append(
            (
                day,
                round(load_by_day[index], 2),
                round(acute, 2),
                round(chronic, 2),
                round(acute / chronic, 3) if reliable else None,
                reliable,
            )
        )

    sessions, blocks = _plan_rows(runs_by_day, today)

    weekly_rows = []
    week_start = start
    while week_start <= today:
        week_runs = [
            r for r in runs if week_start <= r["activity_date"] < week_start + timedelta(days=7)
        ]
        week_sessions = [s for s in sessions if s[1] == week_start and s[17] != "upcoming"]
        targeted = sum(s[12] for s in week_sessions)
        met = sum(s[13] for s in week_sessions)
        verified = sum(s[14] for s in week_sessions)
        compliance = round(100 * met / targeted, 1) if targeted > 0 and verified > 0 else None
        weekly_rows.append(
            (
                week_start,
                len(week_runs),
                round(sum(r["distance_m"] for r in week_runs), 1),
                round(sum(r["duration_s"] for r in week_runs), 1),
                round(sum(r["elev_gain_m"] for r in week_runs), 1),
                round(sum(r["distance_m"] for r in week_runs) / 1000, 2),
                targeted,
                met,
                verified,
                compliance,
            )
        )
        week_start += timedelta(days=7)

    quality_rows = [
        ("silver/activities", len(runs), len(runs), max(r["activity_date"] for r in runs), 0),
        (
            "silver/activity_laps",
            len(runs) * 4,
            len(runs) * 4,
            max(r["activity_date"] for r in runs),
            None,
        ),
        (
            "silver/activity_records",
            len(runs) * 60,
            len(runs) * 60,
            max(r["activity_date"] for r in runs),
            None,
        ),
    ]

    with duckdb.connect(str(target)) as con:
        con.execute("create schema if not exists gold")
        for table, ddl in SCHEMA.items():
            con.execute(f"create table gold.{table} ({ddl})")
        _insert(con, "fct_runs", run_rows)
        _insert(con, "fct_training_load", load_rows)
        _insert(con, "fct_weekly_summary", weekly_rows)
        _insert(con, "fct_plan_sessions", sessions)
        _insert(con, "fct_plan_vs_actual", blocks)
        _insert(con, "mart_data_quality", quality_rows)

    return target
