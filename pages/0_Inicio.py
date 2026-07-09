"""
pages/0_Inicio.py
===================
Landing del portal: qué es, cómo se usa, y un vistazo rápido al catálogo de
datos (cuántos datasets hay, cuántos tienen snapshot disponible ahora mismo).
El catálogo detallado y las descargas viven en la página "Fuentes, descargas
y API"; aquí solo se da una vista general de orientación.
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import loaders, ui  # noqa: E402

ui.header(
    "Portal de Datos SNIGRD",
    "Consulta, visualización, cruce y descarga de datos hidrometeorológicos y de "
    "riesgo municipal para Colombia. Este portal <b>no</b> hace análisis interpretativo: "
    "expone los datos de IDEAM, DANE y UNGRD tal como se publican, listos para cruzar "
    "y descargar.",
)

disponibles = set(loaders.datasets_disponibles())
n_total = len(loaders.CATALOGO)
n_disp = len(disponibles & set(loaders.CATALOGO))
base, _ = loaders.cargar_base_municipal()
n_fuentes_cruzables = len(loaders.fuentes_cruzables())

ui.kpi_row([
    {"label": "Datasets en el catálogo", "value": str(n_total), "icon": "📚"},
    {"label": "Con snapshot disponible", "value": str(n_disp), "icon": "✅"},
    {"label": "Municipios (universo base)", "value": str(len(base)) if base is not None else "—", "icon": "🏘️"},
    {"label": "Fuentes cruzables por DIVIPOLA", "value": str(n_fuentes_cruzables), "icon": "🔗"},
])

st.divider()

c1, c2 = st.columns(2)
with c1:
    st.subheader("¿Qué puedes hacer aquí?")
    st.markdown(
        "- **Cruzar datos por municipio** (código DIVIPOLA): índices de riesgo SNGRD, "
        "emergencias históricas, caracterización DANE, temperatura y amenazas del día — "
        "todo en un mapa y una tabla descargables. → *Consulta y cruce municipal*\n"
        "- **Ver las alertas diarias de IDEAM** (descensos de temperatura, granizo, índice "
        "de calor, temperaturas municipales, amenaza por deslizamientos/incendios/hidrología). "
        "→ *Alertas (datos diarios)*\n"
        "- **Ver observación reciente por estación** (precipitación, temperatura máxima). "
        "→ *Observación diaria*\n"
        "- **Ver pronóstico de corto plazo y estacional (CPT)**. → *Pronóstico*\n"
        "- **Descargar cualquier dataset** en su formato nativo, o consumirlo por API. "
        "→ *Fuentes, descargas y API*"
    )
with c2:
    st.subheader("Cómo se producen los datos")
    st.markdown(
        "Un proceso automático (cron de GitHub Actions) consulta las fuentes oficiales "
        "periódicamente y guarda un **snapshot** de cada dataset en este repositorio "
        "(`data_lake/`). El portal **nunca** consulta IDEAM/DANE en vivo: siempre lee el "
        "último snapshot disponible, con su fecha de actualización visible en cada sección.\n\n"
        "Los datos que aún no tienen fuente nacional verificada (p. ej. algunos campos de "
        "caracterización DANE) se muestran como **pendientes**, nunca se inventan ni se "
        "estiman."
    )

st.divider()
st.caption(
    "¿Buscas el detalle técnico de fuentes, claves de cruce y limitaciones? "
    "Ve a la página **Metodología y fuentes**."
)

ui.footer()
