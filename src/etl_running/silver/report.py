"""Informe de silver: reconciliación con bronze, alcance y cobertura."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from etl_running.silver.build import activities_path, load_summary

COVERAGE_COLUMNS = (
    "avg_hr",
    "max_hr",
    "avg_cadence_spm",
    "stride_m",
    "avg_speed_mps",
    "elev_gain_m",
    "moderate_intensity_min",
    "start_lat",
)


def format_silver_report(silver_dir: Path, running_type_keys: tuple[str, ...]) -> str:
    summary = load_summary(silver_dir)
    if summary is None or not activities_path(silver_dir).is_file():
        return "Silver no construido: ejecuta `etl_running silver build`."
    df = pl.read_parquet(activities_path(silver_dir))

    lines = [
        "Silver · activities",
        f"  Última construcción:  {summary.built_at}",
        f"  Tabla (hash lógico):  {summary.table_hash[:16]}…",
        "",
        "Reconciliación con bronze",
        f"  Registros en bronze (última versión por día): {summary.bronze_records}",
        f"  Versiones antiguas descartadas:               {summary.duplicates_dropped}",
        f"  Actividades únicas:                           {summary.bronze_unique}",
        f"    = silver              {summary.silver}",
        f"    + cuarentena          {summary.quarantine}",
        f"    + out_of_scope        {summary.out_of_scope_total}",
        f"  Cuadra: {'sí' if summary.reconciles else 'NO'}",
    ]
    if summary.out_of_scope:
        lines += ["", "out_of_scope por typeKey (descartados, no es error)"]
        for type_key, count in sorted(summary.out_of_scope.items(), key=lambda kv: -kv[1]):
            hint = "  ← ¿es una carrera? revisa RUNNING_TYPE_KEYS" if "run" in type_key else ""
            lines.append(f"  {type_key:<24} {count:>5}{hint}")
    if summary.warnings:
        lines.append(f"\nAvisos (valores fuera de rango guardados como NULL): {summary.warnings}")

    lines += ["", f"Actividades en silver: {df.height}"]
    if df.height:
        lines += [
            f"  Rango (fecha local):  {df['local_date'].min()} → {df['local_date'].max()}",
            f"  Manuales:             {int(df['is_manual'].sum())}",
            f"  Sin GPS:              {int((~df['has_gps']).sum())}",
            "  Por typeKey:          "
            + ", ".join(
                f"{r['activity_type']}={r['count']}"
                for r in df["activity_type"]
                .value_counts()
                .sort("count", descending=True)
                .to_dicts()
            ),
            "",
            "Cobertura (% de actividades con dato)",
        ]
        for column in COVERAGE_COLUMNS:
            pct = 100 * (df.height - df[column].null_count()) / df.height
            lines.append(f"  {column:<24} {pct:5.1f}%")
    if not set(df["activity_type"].unique()) <= set(running_type_keys):
        lines.append("ADVERTENCIA: silver contiene tipos fuera de RUNNING_TYPE_KEYS actuales.")
    return "\n".join(lines)
