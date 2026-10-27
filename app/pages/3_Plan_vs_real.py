"""Dashboard ETL Running — Plan vs real por semana."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from app import queries, ui

ui.setup("Plan vs real")

try:
    weeks = queries.plan_weeks()
except queries.DashboardError as exc:
    ui.data_error(exc)
    st.stop()

if not weeks:
    st.info("No hay semanas de plan en Gold. Carga un JSON con `etl_running plan load`.")
    st.stop()

week = st.sidebar.selectbox(
    "Semana",
    weeks,
    index=min(1, len(weeks) - 1),
    format_func=lambda value: pd.Timestamp(value).strftime("Semana del %d/%m/%Y"),
)
st.caption(
    "Por defecto se muestra la última semana cerrada; la semana en curso queda en el selector."
)
try:
    sessions = queries.plan_sessions(week)
    blocks = queries.plan_blocks(week)
    week_summary = queries.plan_week_summary(week)
except queries.DashboardError as exc:
    ui.data_error(exc)
    st.stop()

targeted = week_summary["targeted_steps"]
met = week_summary["steps_met"]
verified = week_summary["verified_steps"]
compliance = week_summary["plan_compliance_pct"]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Sesiones", len(sessions))
c2.metric("Cumplidas", int((sessions["status"] == "done").sum()))
c3.metric(
    "Bloques OK",
    f"{met}/{targeted}" if targeted else "—",
    help=f"{verified} bloques con evidencia verificable.",
)
c4.metric("Cumplimiento", ui.fmt_pct(compliance))

st.subheader("Sesiones")
if sessions.empty:
    st.info("Sin sesiones para esta semana.")
else:
    display = sessions.copy()
    display["status"] = display["status"].map(ui.status_label)
    display["date_offset_days"] = display["date_offset_days"].fillna(0).astype(int)
    display = display.rename(
        columns={
            "scheduled_date": "Planificada",
            "title": "Sesión",
            "status": "Estado",
            "activity_date": "Real",
            "date_offset_days": "Desplazamiento (días)",
            "confirmed_by_user": "Confirmada",
            "confidence": "Confianza",
            "steps_met": "Bloques OK",
            "targeted_steps": "Objetivos",
            "verified_steps": "Verificados",
        }
    )
    columns = [
        "Planificada",
        "Sesión",
        "Estado",
        "Real",
        "Desplazamiento (días)",
        "Confirmada",
        "Confianza",
        "Bloques OK",
        "Objetivos",
        "Verificados",
    ]
    ui.table(display[columns])

st.subheader("Detalle por bloque")
if blocks.empty:
    st.info("Sin bloques de plan para esta semana.")
else:
    for _, session in sessions.iterrows():
        title = (
            f"{ui.fmt_date(session['scheduled_date'])} · {session['title']} · "
            f"{ui.status_label(session['status'])}"
        )
        with st.expander(title):
            detail = blocks[blocks["planned_workout_id"] == session["planned_workout_id"]].copy()
            if detail.empty:
                st.caption("Sin pasos detallados.")
                continue
            detail["Objetivo"] = detail.apply(
                lambda row: (
                    f"{ui.fmt_pace(row['pace_fast_s_km'] / 60)}–"
                    f"{ui.fmt_pace(row['pace_slow_s_km'] / 60)} /km"
                    if pd.notna(row["pace_fast_s_km"]) and pd.notna(row["pace_slow_s_km"])
                    else "—"
                ),
                axis=1,
            )
            detail["Real"] = detail["actual_pace_s_km"].map(
                lambda value: ui.fmt_pace(value / 60) if pd.notna(value) else "—"
            )
            detail["Estado"] = detail["pace_status"].map(ui.pace_status_label)
            detail = detail.rename(
                columns={
                    "kind": "Bloque",
                    "repetition": "Rep.",
                    "target_distance_m": "Distancia objetivo (m)",
                    "confidence": "Confianza",
                }
            )
            ui.table(
                detail[
                    [
                        "Bloque",
                        "Rep.",
                        "Distancia objetivo (m)",
                        "Objetivo",
                        "Real",
                        "Estado",
                        "Confianza",
                    ]
                ]
            )

st.caption(
    "Una sesión desplazada ±1 día aparece solo si se confirma manualmente con "
    "`etl_running plan confirm`; el plan no se infiere por fecha."
)
