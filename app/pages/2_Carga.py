"""Dashboard ETL Running — Carga aguda, crónica y ACWR."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st
from app import queries, ui

ui.setup("Carga")

try:
    days = st.sidebar.select_slider(
        "Ventana", options=[60, 90, 120, 180], value=120, format_func=lambda d: f"{d} días"
    )
    frame = queries.training_load(days)
except queries.DashboardError as exc:
    ui.data_error(exc)
    st.stop()

if frame.empty:
    st.info("No hay datos de carga en esta ventana.")
    st.stop()

latest = frame.iloc[-1]
c1, c2, c3 = st.columns(3)
c1.metric(
    "ACWR",
    f"{latest['acwr']:.2f}" if pd.notna(latest["acwr"]) else "—",
    help="Aguda 7 días / crónica 28 días. Solo fiable con 28 días completos.",
)
c2.metric("Carga aguda", f"{latest['acute_7d']:.1f}" if pd.notna(latest["acute_7d"]) else "—")
c3.metric(
    "Carga crónica", f"{latest['chronic_28d']:.1f}" if pd.notna(latest["chronic_28d"]) else "—"
)
if not bool(latest["is_reliable"]):
    st.warning("ACWR aún no es fiable: faltan 28 días completos de carga.")
else:
    st.caption(
        "Zona habitual: 0,8–1,3 · Precaución: 1,3–1,5 · Riesgo elevado: >1,5. "
        "No es un diagnóstico médico."
    )

st.subheader("Carga aguda y crónica")
st.line_chart(
    frame.set_index("activity_date")[["acute_7d", "chronic_28d"]],
    height=300,
    color=["#ef6c00", "#1565c0"],
)

st.subheader("ACWR")
reliable = frame.dropna(subset=["acwr"])
if reliable.empty:
    st.info("Sin ACWR fiable todavía.")
else:
    base = (
        alt.Chart(reliable)
        .mark_line(color="#6a1b9a", strokeWidth=2)
        .encode(
            x=alt.X("activity_date:T", title="Fecha"),
            y=alt.Y("acwr:Q", title="ACWR", scale=alt.Scale(domain=[0, 2])),
            tooltip=["activity_date:T", alt.Tooltip("acwr:Q", format=".2f")],
        )
        .properties(height=300)
    )
    rules = (
        alt.Chart(pd.DataFrame({"limite": [0.8, 1.3, 1.5], "zona": ["0,8", "1,3", "1,5"]}))
        .mark_rule(strokeDash=[5, 4])
        .encode(y="limite:Q", color=alt.Color("zona:N", title="Límite"))
    )
    st.altair_chart(base + rules, width="stretch")

with st.expander("Qué significa ACWR"):
    st.markdown(
        """
        El **ACWR** compara la carga de los últimos 7 días con la media de 28 días.
        Sube cuando aumentas volumen o intensidad más rápido de lo que tu cuerpo
        ha asimilado. Se calcula en Gold con minutos moderados + 2× vigorosos;
        las semanas sin datos suficientes quedan fuera.
        """
    )
