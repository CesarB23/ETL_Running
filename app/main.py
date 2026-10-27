"""Punto de entrada del dashboard: navegación explícita y páginas de solo lectura."""

from __future__ import annotations

import streamlit as st

pages = [
    st.Page("pages/0_Resumen.py", title="Resumen", icon="📊"),
    st.Page("pages/1_Progreso.py", title="Progreso", icon="📈"),
    st.Page("pages/2_Carga.py", title="Carga", icon="⚖️"),
    st.Page("pages/3_Plan_vs_real.py", title="Plan vs real", icon="🎯"),
    st.Page("pages/4_Salud_pipeline.py", title="Salud del pipeline", icon="🩺"),
]
navigation = st.navigation(pages)
navigation.run()
