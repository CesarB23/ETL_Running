"""Gráfica SVG/HTML local para ritmo, FC y cadencia, más tabla de laps."""

from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

import polars as pl


def _line(
    values: list[float | None], color: str, times: list[datetime], running: list[bool]
) -> str:
    values = [value if active else None for value, active in zip(values, running, strict=True)]
    valid = [(i, value) for i, value in enumerate(values) if value is not None]
    if not valid:
        return ""
    low, high = min(value for _, value in valid), max(value for _, value in valid)
    span = high - low or 1
    width = max(len(values) - 1, 1)
    # Segmentos separados para no unir huecos ni pausas artificialmente.
    fragments: list[list[str]] = []
    for i, value in enumerate(values):
        if value is None:
            continue
        if i == 0 or values[i - 1] is None or (times[i] - times[i - 1]).total_seconds() > 5:
            fragments.append([])
        x = 45 + i * 850 / width
        y = 175 - (value - low) * 145 / span
        fragments[-1].append(f"{x:.1f},{y:.1f}")
    return "".join(
        f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{part}"/>'
        for part in (" ".join(points) for points in fragments)
    )


def render_run(silver_dir: Path, activity_id: int, out: Path) -> Path:
    records_path = silver_dir / "activity_records.parquet"
    laps_path = silver_dir / "activity_laps.parquet"
    if not records_path.exists() or not laps_path.exists():
        raise FileNotFoundError(
            "Faltan laps/records: ejecuta silver build --only activity_laps activity_records"
        )
    recs = pl.read_parquet(records_path).filter(pl.col("activity_id") == activity_id).sort("ts_utc")
    laps = pl.read_parquet(laps_path).filter(pl.col("activity_id") == activity_id).sort("lap_index")
    if recs.is_empty() and laps.is_empty():
        raise ValueError("Actividad sin FIT procesado")
    times = recs["ts_utc"].to_list()
    timer_running = recs["timer_running"].to_list()
    traces = [
        (
            "Ritmo (min/km)",
            "#2563eb",
            [round(1000 / s / 60, 2) if s and s > 0 else None for s in recs["speed_mps"]],
        ),
        ("Frecuencia cardíaca (lpm)", "#dc2626", recs["heart_rate"].to_list()),
        ("Cadencia (spm)", "#16a34a", recs["cadence_spm"].to_list()),
    ]
    figures = []
    for label, color, values in traces:
        figures.append(
            f"<h2>{escape(label)}</h2>"
            f'<svg viewBox="0 0 920 200" role="img" aria-label="{escape(label)}">'
            f'<path d="M45 175 H900" stroke="#999"/>'
            f"{_line(values, color, times, timer_running)}</svg>"
        )
    body = ""
    for row in laps.iter_rows(named=True):
        cells = (
            row["lap_index"] + 1,
            row["wkt_step_index"],
            row["intensity"],
            row["distance_m"],
            row["duration_s"],
        )
        body += (
            "<tr>"
            + "".join(f"<td>{escape(str(v)) if v is not None else '-'}</td>" for v in cells)
            + "</tr>"
        )
    html = (
        '<!doctype html><html lang="es"><meta charset="utf-8"><title>Carrera FIT</title>'
        "<style>body{font:16px system-ui;max-width:1000px;margin:auto;padding:1rem}"
        "svg{width:100%;border:1px solid #ddd}td,th{padding:.5rem;border:1px solid #ddd}</style>"
        f"<h1>Carrera {activity_id}</h1>"
        + "".join(figures)
        + "<h2>Laps</h2><table><tr><th>#</th><th>Paso workout</th>"
        "<th>Intensidad</th><th>Metros</th><th>Segundos</th></tr>" + body + "</table></html>"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out
