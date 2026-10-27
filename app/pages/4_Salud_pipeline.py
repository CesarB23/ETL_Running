"""Dashboard ETL Running — salud del pipeline y alertas locales."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st
from app import queries, ui

ui.setup("Salud del pipeline")

try:
    quality = queries.data_quality()
except queries.DashboardError as exc:
    ui.data_error(exc)
    st.stop()

st.subheader("Frescura")
c1, c2 = st.columns(2)
c1.metric("Warehouse actualizado", ui.last_update())
c2.metric("Hoy", date.today().strftime("%d/%m/%Y"))
st.caption(
    "La antigüedad se calcula sobre el archivo `warehouse.duckdb`, no sobre la última carrera."
)

st.subheader("Calidad por dataset")
if quality.empty:
    st.info("`mart_data_quality` está vacío.")
else:
    display = quality.rename(
        columns={
            "dataset": "Dataset",
            "row_count": "Filas",
            "distinct_keys": "Claves únicas",
            "max_activity_date": "Última fecha",
            "rejected_count": "Rechazadas",
        }
    )
    ui.table(display)

    for _, row in quality.iterrows():
        if row["row_count"] == 0:
            st.warning(f"{row['dataset']} no tiene filas.")
        if row["max_activity_date"] is not None and pd.notna(row["max_activity_date"]):
            age = (date.today() - pd.Timestamp(row["max_activity_date"]).date()).days
            if age > 10:
                st.warning(f"{row['dataset']} no tiene datos nuevos desde hace {age} días.")

st.subheader("Alertas")
lines = queries.alerts_tail()
if lines:
    st.code("\n".join(lines), language="text")
else:
    st.info("Todavía no hay `lake/alerts.log`. Ejecuta `make alerts` para evaluar las reglas.")
st.caption("Las alertas se escriben en `lake/alerts.log`; no se envían a servicios externos.")

with st.expander("Reglas activas"):
    st.markdown(
        """
        - ACWR > 1,5 con ventana fiable.
        - Más de 10 días sin carrera.
        - Cumplimiento del plan < 50 % en la última semana cerrada.
        - Warehouse sin actualizar > 36 h.
        - API key de Garmin caducada o a menos de 14 días (si se informa la fecha).
        """
    )

st.subheader("Actualizar")
st.code(
    "make ingest\nmake silver\nmake dbt-build\nmake alerts",
    language="bash",
)
