"""Dashboard ETL Running — Progreso de ritmo y eficiencia."""

from __future__ import annotations

import streamlit as st
from app import queries, ui

ui.setup("Progreso")

try:
    days = st.sidebar.select_slider(
        "Ventana", options=[30, 60, 90, 120, 180], value=120, format_func=lambda d: f"{d} días"
    )
    frame = queries.progress(days)
except queries.DashboardError as exc:
    ui.data_error(exc)
    st.stop()

if frame.empty:
    st.info("No hay actividades válidas para ritmo en esta ventana.")
    st.stop()

valid = frame.dropna(subset=["pace_min_km"])
if not valid.empty:
    latest = valid.iloc[-1]
    best = valid["pace_min_km"].min()
    c1, c2, c3 = st.columns(3)
    c1.metric("Último ritmo", f"{ui.fmt_pace(latest['pace_min_km'])} /km")
    c2.metric("Mejor ritmo", f"{ui.fmt_pace(best)} /km")
    c3.metric(
        "Eficiencia media",
        f"{valid['aerobic_efficiency'].mean():.4f}"
        if valid["aerobic_efficiency"].notna().any()
        else "—",
        help="Velocidad media (m/s) / FC media. Más alto es mejor.",
    )

st.subheader("Ritmo")
if valid.empty:
    st.info("Sin ritmos válidos.")
else:
    st.line_chart(
        valid.set_index("activity_date")[["pace_min_km"]].rename(columns={"pace_min_km": "min/km"}),
        height=280,
        color="#1565c0",
    )
    st.caption(
        "Eje Y en minutos por kilómetro: menos es mejor. Solo actividades válidas para ritmo."
    )

st.subheader("Eficiencia aeróbica")
efficiency = frame.dropna(subset=["aerobic_efficiency"])
if efficiency.empty:
    st.info("Sin eficiencia aeróbica válida.")
else:
    st.line_chart(
        efficiency.set_index("activity_date")[["aerobic_efficiency"]].rename(
            columns={"aerobic_efficiency": "m/s por lpm"}
        ),
        height=260,
        color="#6a1b9a",
    )

st.subheader("Drift cardíaco")
drift = frame.dropna(subset=["cardiac_drift_pct"])
if drift.empty:
    st.info("Sin datos de drift válidos.")
else:
    st.line_chart(
        drift.set_index("activity_date")[["cardiac_drift_pct"]].rename(
            columns={"cardiac_drift_pct": "%"}
        ),
        height=240,
        color="#ef6c00",
    )
    st.caption(
        "Variación de eficiencia entre las dos mitades de la carrera. "
        "Un drift alto con el mismo ritmo sugiere fatiga o calor."
    )

st.subheader("Detalle")
display = frame.rename(
    columns={
        "activity_date": "Fecha",
        "pace_min_km": "Ritmo",
        "aerobic_efficiency": "Eficiencia",
        "cardiac_drift_pct": "Drift %",
        "avg_hr": "FC media",
    }
)
display["Ritmo"] = display["Ritmo"].map(ui.fmt_pace)
ui.table(display)
