"""Utilidades compartidas por las páginas del dashboard."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from app import queries


def setup(title: str) -> None:
    st.set_page_config(
        page_title=f"{title} · ETL Running",
        page_icon="🏃",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.title(title)
    if queries.demo_mode():
        st.info(
            "Modo demo: este warehouse es sintético y no contiene datos personales. "
            "Desactiva `DEMO_MODE` para leer `lake/warehouse.duckdb`."
        )
    path = queries.warehouse_path()
    st.sidebar.caption(f"Fuente: `{path}`")
    st.sidebar.caption("Solo lectura sobre Gold · sin GPS ni datos de salud.")


def data_error(exc: Exception) -> None:
    st.error(str(exc))
    st.markdown(
        """
        Para generar datos reales:

        ```bash
        make ingest
        make silver
        make dbt-build
        ```

        Para probar sin datos personales:

        ```bash
        make demo
        DEMO_MODE=1 make app
        ```
        """
    )


def fmt_pace(minutes_per_km: float | None) -> str:
    if minutes_per_km is None or pd.isna(minutes_per_km):
        return "—"
    total = round(float(minutes_per_km) * 60)
    return f"{total // 60}:{total % 60:02d}"


def fmt_date(value: date | datetime | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    return pd.Timestamp(value).strftime("%d/%m/%Y")


def fmt_hours(hours: float | None) -> str:
    if hours is None or pd.isna(hours):
        return "—"
    return f"{float(hours):.1f} h"


def fmt_pct(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{float(value):.1f}%"


def table(frame: pd.DataFrame, *, height: int | None = None) -> None:
    options: dict[str, object] = {"hide_index": True, "width": "stretch"}
    if height is not None:
        options["height"] = height
    st.dataframe(frame, **options)


def last_update(path: Path | None = None) -> str:
    target = path or queries.warehouse_path()
    if not target.is_file():
        return "sin warehouse"
    return datetime.fromtimestamp(target.stat().st_mtime).strftime("%d/%m/%Y %H:%M")


def status_label(value: str) -> str:
    return {
        "done": "Cumplida",
        "partial": "Parcial",
        "missed": "No realizada",
        "upcoming": "Próxima",
    }.get(value, value)


def pace_status_label(value: str) -> str:
    return {
        "met": "Dentro del ritmo",
        "not_met": "Fuera del ritmo",
        "unverifiable": "No verificable",
        "not_targeted": "Sin ritmo objetivo",
    }.get(value, value)
