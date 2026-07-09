"""
app.py — Router del portal
=============================
Único lugar donde se llama st.set_page_config. Define la navegación
(st.navigation/st.Page) y la marca en el sidebar (logo + nombre); el
contenido de cada sección vive en pages/*.py.
"""
import streamlit as st

from src import ui

st.set_page_config(
    page_title="UNGRD · Portal de Datos SNIGRD",
    page_icon="🗂️",
    layout="wide",
)

ui.sidebar_brand()

paginas = [
    st.Page("pages/0_Inicio.py", title="Inicio y catálogo", icon="🗂️", default=True),
    st.Page("pages/1_Consulta_cruce_municipal.py", title="Consulta y cruce municipal", icon="🔎"),
    st.Page("pages/2_Alertas.py", title="Alertas (datos diarios)", icon="🚨"),
    st.Page("pages/3_Observacion_diaria.py", title="Observación diaria", icon="🌡️"),
    st.Page("pages/4_Pronostico.py", title="Pronóstico", icon="📈"),
    st.Page("pages/5_Fuentes_descargas_API.py", title="Fuentes, descargas y API", icon="📂"),
    st.Page("pages/6_Metodologia_y_fuentes.py", title="Metodología y fuentes", icon="📖"),
]

st.navigation(paginas).run()
