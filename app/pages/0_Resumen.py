"""Dashboard ETL Running — página de Resumen."""

from __future__ import annotations

import streamlit as st
from app import queries, ui

ui.setup("Resumen")

try:
    snapshot = queries.latest_snapshot()
    weekly = queries.weekly_summary()
    recent = queries.recent_runs()
except queries.DashboardError as exc:
    ui.data_error(exc)
    st.stop()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Km últimos 7 días", f"{snapshot['km_7d'] or 0:.1f}")
col2.metric("Carreras", f"{snapshot['runs_7d'] or 0}")
col3.metric("Tiempo", ui.fmt_hours(snapshot["hours_7d"]))
col4.metric(
    "ACWR",
    f"{snapshot['acwr']:.2f}" if snapshot["acwr"] is not None else "—",
    help="Carga aguda (7 días) / crónica (28 días). Solo se muestra si es fiable.",
)
col5.metric("Cumplimiento plan", ui.fmt_pct(snapshot["plan_compliance_pct"]))
st.caption(f"Última carrera: {ui.fmt_date(snapshot['last_run_date'])} · {ui.last_update()}")

st.subheader("Volumen semanal")
if weekly.empty:
    st.info("Todavía no hay semanas en Gold.")
else:
    chart = weekly.set_index("week_start")[["distance_km"]].rename(columns={"distance_km": "km"})
    st.bar_chart(chart, height=280, color="#2e7d32")
    st.caption("Kilómetros de carreras no manuales, agregados por semana ISO.")

left, right = st.columns([2, 1])
with left:
    st.subheader("Últimas carreras")
    if recent.empty:
        st.info("No hay actividades en el periodo.")
    else:
        display = recent.rename(
            columns={
                "activity_date": "Fecha",
                "activity_type": "Tipo",
                "km": "Km",
                "minutes": "Minutos",
                "pace_min_km": "Ritmo",
                "avg_hr": "FC media",
                "aerobic_efficiency": "Eficiencia",
            }
        )
        display["Ritmo"] = display["Ritmo"].map(ui.fmt_pace)
        ui.table(display, height=360)
with right:
    st.subheader("Cómo leerlo")
    st.markdown(
        """
        - **ACWR** entre 0,8 y 1,3 es una zona habitual de seguridad.
        - Por encima de **1,5** el riesgo de sobrecarga sube.
        - El cumplimiento solo cuenta bloques verificables del plan.
        - Los datos salen de Gold: la app no recalcula entrenamientos.
        """
    )
