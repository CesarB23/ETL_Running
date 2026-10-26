"""Informe de bronze: filas, rango, frescura, errores y desglose por `typeKey`."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from etl_running.bronze.writer import BronzeWriter


@dataclass
class DatasetReport:
    dataset: str
    files: int = 0
    rows: int = 0
    min_dt: date | None = None
    max_dt: date | None = None
    last_ingested_at: datetime | None = None
    errors: int = 0
    type_counts: Counter[str] = field(default_factory=Counter)


def _count_errors(runs_log: Path) -> Counter[str]:
    errors: Counter[str] = Counter()
    if runs_log.is_file():
        for line in runs_log.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entry = json.loads(line)
                if entry.get("status") == "error":
                    errors[entry["dataset"]] += 1
    return errors


def build_report(bronze_dir: Path, runs_log: Path) -> list[DatasetReport]:
    """Una fila por dataset. `rows` y `type_counts` usan la última versión de cada `dt`."""
    writer = BronzeWriter(bronze_dir)
    manifest = writer.read_manifest().to_pylist()
    errors = _count_errors(runs_log)

    reports: dict[str, DatasetReport] = {}
    latest: dict[tuple[str, date], dict] = {}
    for row in manifest:
        key = f"{row['source']}/{row['dataset']}"
        rep = reports.setdefault(key, DatasetReport(key))
        rep.files += 1
        if rep.last_ingested_at is None or row["ingested_at"] > rep.last_ingested_at:
            rep.last_ingested_at = row["ingested_at"]
        current = latest.get((key, row["dt"]))
        if current is None or row["ingested_at"] > current["ingested_at"]:
            latest[(key, row["dt"])] = row

    for (key, dt), row in latest.items():
        rep = reports[key]
        rep.rows += row["n_records"]
        rep.min_dt = dt if rep.min_dt is None else min(rep.min_dt, dt)
        rep.max_dt = dt if rep.max_dt is None else max(rep.max_dt, dt)
        payload = json.loads((bronze_dir / row["path"]).read_text(encoding="utf-8"))
        for item in payload:
            type_key = (item.get("activityType") or {}).get("typeKey") or "desconocido"
            rep.type_counts[type_key] += 1

    for key, count in errors.items():
        reports.setdefault(key, DatasetReport(key)).errors = count
    return sorted(reports.values(), key=lambda r: r.dataset)


def format_report(
    reports: Iterable[DatasetReport],
    running_type_keys: Iterable[str],
    today: date | None = None,
) -> str:
    today = today or datetime.now(UTC).date()
    running = set(running_type_keys)
    reports = list(reports)
    if not reports:
        return "Bronze vacío: ejecuta `etl_running backfill`."

    header = ("dataset", "archivos", "filas", "min_dt", "max_dt", "frescura", "errores")
    rows = [header]
    for r in reports:
        fresh = "-"
        if r.last_ingested_at:
            age = (today - r.last_ingested_at.date()).days
            fresh = f"{age}d (último {r.last_ingested_at:%Y-%m-%d %H:%M}Z)"
        rows.append(
            (
                r.dataset,
                str(r.files),
                str(r.rows),
                str(r.min_dt or "-"),
                str(r.max_dt or "-"),
                fresh,
                str(r.errors),
            )
        )
    widths = [max(len(row[i]) for row in rows) for i in range(len(header))]
    lines = ["  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)) for row in rows]
    lines.insert(1, "  ".join("-" * w for w in widths))

    for r in reports:
        if r.type_counts:
            in_scope = sum(c for k, c in r.type_counts.items() if k in running)
            lines.append("")
            lines.append(f"Desglose por typeKey en {r.dataset} (total {r.rows}):")
            for type_key, count in r.type_counts.most_common():
                scope = "running" if type_key in running else "out_of_scope"
                lines.append(f"  {type_key:<24} {count:>5}  {scope}")
            lines.append(f"  {'en alcance (running)':<24} {in_scope:>5}")
    return "\n".join(lines)


def latest_activities(bronze_dir: Path, since: date) -> list[dict]:
    """Actividades con `dt >= since`, usando la última versión de cada partición."""
    latest: dict[date, dict] = {}
    for row in BronzeWriter(bronze_dir).read_manifest().to_pylist():
        if row["dataset"] != "activities_list" or row["dt"] < since:
            continue
        if row["dt"] not in latest or row["ingested_at"] > latest[row["dt"]]["ingested_at"]:
            latest[row["dt"]] = row
    activities: list[dict] = []
    for row in latest.values():
        activities.extend(json.loads((bronze_dir / row["path"]).read_text(encoding="utf-8")))
    return sorted(activities, key=lambda a: str(a.get("startTimeLocal")))


def _clock(seconds: float | None) -> str:
    if not seconds:
        return "-"
    total = round(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def format_activities(activities: Iterable[dict], running_type_keys: Iterable[str]) -> str:
    running = set(running_type_keys)
    header = ("inicio", "tipo", "km", "duración", "ritmo/km", "FC media", "nota")
    rows = [header]
    for a in activities:
        type_key = (a.get("activityType") or {}).get("typeKey") or "desconocido"
        distance, duration = a.get("distance"), a.get("duration")
        km = f"{distance / 1000:.2f}" if distance else "-"
        pace = _clock(duration / (distance / 1000)) if distance and duration else "-"
        hr = f"{a['averageHR']:.0f}" if a.get("averageHR") else "-"
        notes = []
        if a.get("manualActivity"):
            notes.append("manual")
        if type_key not in running:
            notes.append("out_of_scope")
        rows.append(
            (
                str(a.get("startTimeLocal", ""))[:16],
                type_key,
                km,
                _clock(duration),
                pace,
                hr,
                ", ".join(notes),
            )
        )
    if len(rows) == 1:
        return "Sin actividades en ese periodo (¿ya ejecutaste backfill/ingest?)."
    widths = [max(len(r[i]) for r in rows) for i in range(len(header))]
    lines = ["  ".join(c.ljust(widths[i]) for i, c in enumerate(r)).rstrip() for r in rows]
    lines.insert(1, "  ".join("-" * w for w in widths))
    return "\n".join(lines)
