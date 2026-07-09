"""
pages/3_Observacion_diaria.py
===============================
Observación reciente por estación (precipitación y temperatura máxima
diarias, red de estaciones IDEAM/ArcGIS OSPA). Los reportes diarios del
árbol /ospa/Alertas/ (BART) viven en la página "Alertas (datos diarios)".
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import loaders, ui  # noqa: E402
from src.maps import capa_puntos, mapa_base, mostrar_mapa  # noqa: E402
from src.downloads import boton_csv, boton_geojson  # noqa: E402

ui.header(
    "Observación diaria",
    "Precipitación y temperatura máxima registradas por estación (red IDEAM, ArcGIS OSPA).",
)

variable = st.radio("Variable", ["Precipitación diaria", "Temperatura máxima diaria"], horizontal=True)
ds = "precipitacion_diaria" if variable == "Precipitación diaria" else "temperatura_max_diaria"
color = "#1F6FEB" if ds == "precipitacion_diaria" else "#D7263D"
unidad = "mm" if ds == "precipitacion_diaria" else "°C"

geo = loaders.cargar_geojson(ds)
tabla = loaders.cargar_tabla(ds)
meta = loaders.metadatos(ds)

if geo is None or tabla is None:
    ui.sin_datos(ds)
else:
    deptos = sorted(tabla["DEPARTAMEN"].dropna().unique())
    depto_sel = st.selectbox("Departamento", ["Todos"] + deptos, key=f"depto_{ds}")
    tabla_f = tabla if depto_sel == "Todos" else tabla[tabla["DEPARTAMEN"] == depto_sel]
    codigos = set(tabla_f["CODIGO"])
    geo_f = {"type": "FeatureCollection",
             "features": [f for f in geo["features"] if f["properties"].get("CODIGO") in codigos]}

    ui.kpi_row([
        {"label": "Estaciones", "value": str(len(tabla_f)), "icon": "📍"},
        {"label": f"Promedio ({unidad})", "value": f"{tabla_f['DATO'].mean():.1f}" if len(tabla_f) else "—", "icon": "📊"},
        {"label": f"Máximo ({unidad})", "value": f"{tabla_f['DATO'].max():.1f}" if len(tabla_f) else "—", "icon": "🔺",
         "sub": str(tabla_f.loc[tabla_f["DATO"].idxmax(), "ESTACION"]) if len(tabla_f) else ""},
        {"label": f"Mínimo ({unidad})", "value": f"{tabla_f['DATO'].min():.1f}" if len(tabla_f) else "—", "icon": "🔻"},
    ])

    col_map, col_tabla = st.columns([3, 2])
    with col_map:
        m = mapa_base()
        capa_puntos(
            m, geo_f,
            tooltip_fields=["ESTACION", "MUNICIPIO", "DEPARTAMEN", "DATO", "CATEGORIA"],
            tooltip_aliases=["Estación", "Municipio", "Departamento", f"Dato ({unidad})", "Categoría"],
            nombre=variable, color=color,
        )
        mostrar_mapa(m, key=f"mapa_{ds}")
        ui.meta_caption(meta)
    with col_tabla:
        cols = ["ESTACION", "MUNICIPIO", "DEPARTAMEN", "DATO", "CATEGORIA"]
        st.dataframe(
            tabla_f[cols].rename(columns={
                "ESTACION": "Estación", "MUNICIPIO": "Municipio", "DEPARTAMEN": "Departamento",
                "DATO": f"Dato ({unidad})", "CATEGORIA": "Categoría",
            }).sort_values(f"Dato ({unidad})", ascending=False),
            hide_index=True, width="stretch", height=430,
        )

    c1, c2 = st.columns(2)
    with c1:
        boton_csv(tabla_f, f"{ds}.csv", key=f"csv_{ds}")
    with c2:
        boton_geojson(geo_f, f"{ds}.geojson", key=f"geojson_{ds}")

ui.footer()
