"""
pages/1_Consulta_cruce_municipal.py
=====================================
Núcleo del portal: cruce de datos municipales por código DIVIPOLA. El
universo base son los 1.122 municipios de la capa de índices de riesgo
SNGRD (única fuente con geometría de polígono utilizable para mapa
coroplético); el usuario elige qué fuentes cruzar y qué variable visualizar.

No inventa cruces: un municipio ausente en una fuente queda "sin dato" (NaN),
nunca relleno ni estimado. El reporte de no-cruce se escribe a
data_lake/_diagnostico/divipola_no_cruza.csv para auditoría.
"""
import sys
from pathlib import Path

import branca.colormap as cm
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import loaders, ui  # noqa: E402
from src.maps import mapa_base, mostrar_mapa, capa_vector_coloreada, agregar_leyenda  # noqa: E402
from src.downloads import boton_csv, boton_geojson  # noqa: E402

DIAG_PATH = Path(__file__).resolve().parents[1] / "data_lake" / "_diagnostico" / "divipola_no_cruza.csv"

ui.header(
    "Consulta y cruce municipal",
    "Cruza índices de riesgo SNGRD, emergencias históricas, caracterización DANE y "
    "alertas/amenazas diarias de IDEAM por código <b>DIVIPOLA</b>. Elige las fuentes, "
    "filtra por departamento/municipio y descarga el resultado.",
)

fuentes_meta = loaders.fuentes_cruzables()
if not fuentes_meta:
    st.warning("No hay fuentes cruzables registradas todavía.")
    st.stop()

fuentes_sel = st.multiselect(
    "Fuentes a cruzar",
    options=list(fuentes_meta.keys()),
    default=list(fuentes_meta.keys()),
    format_func=lambda fid: fuentes_meta[fid]["nombre"],
    help="Cada fuente se cruza por DIVIPOLA (código de 5 dígitos) sobre el universo "
         "de 1.122 municipios de la capa de riesgo SNGRD.",
)

if not fuentes_sel:
    st.info("Elige al menos una fuente para cruzar.")
    st.stop()

base, geo_base = loaders.cargar_base_municipal()
df = loaders.cruzar_fuentes(tuple(sorted(fuentes_sel)))

# --------------------------------------------------------------------------- #
# Filtros en cascada
# --------------------------------------------------------------------------- #
fc1, fc2 = st.columns(2)
with fc1:
    deptos = sorted(df["departamento"].dropna().unique())
    depto_sel = st.selectbox("Departamento", ["Todos"] + deptos)
df_f = df if depto_sel == "Todos" else df[df["departamento"] == depto_sel]
with fc2:
    munis = sorted(df_f["municipio"].dropna().unique())
    muni_sel = st.multiselect("Municipio (opcional, filtra la tabla y el mapa)", munis)
if muni_sel:
    df_f = df_f[df_f["municipio"].isin(muni_sel)]

# --------------------------------------------------------------------------- #
# Variable a visualizar en el mapa
# --------------------------------------------------------------------------- #
columnas_cruzadas = [c for c in df.columns if c not in ("divipola", "municipio", "departamento")]
if not columnas_cruzadas:
    st.info("Las fuentes elegidas no aportaron columnas.")
    st.stop()

var_sel = st.selectbox(
    "Variable a visualizar en el mapa",
    columnas_cruzadas,
    format_func=lambda c: c.replace("__", " · "),
)

sin_dato = df_f[var_sel].isna().sum()
con_dato = len(df_f) - sin_dato

ui.kpi_row([
    {"label": "Municipios en la selección", "value": str(len(df_f)), "icon": "🏘️"},
    {"label": "Con dato en la variable elegida", "value": str(con_dato), "icon": "✅"},
    {"label": "Sin dato (no cruza / no aplica)", "value": str(sin_dato), "icon": "⚪"},
])

col_map, col_tabla = st.columns([3, 2])

es_numerica = pd.api.types.is_numeric_dtype(df_f[var_sel])

with col_map:
    m = mapa_base()
    geo_f = loaders.geojson_con_atributos(df_f, geo_base)
    # sólo los municipios de la selección actual quedan en el geojson filtrado
    codigos_f = set(df_f["divipola"])
    geo_f = {
        "type": "FeatureCollection",
        "features": [f for f in geo_f["features"]
                      if str(f["properties"].get("MPIO_CCNCT", "")).strip().zfill(5) in codigos_f],
    }

    if es_numerica:
        valores = df_f[var_sel].dropna()
        if len(valores) > 0:
            colormap = cm.LinearColormap(
                colors=["#F2F4F8", "#1F3460"],
                vmin=float(valores.min()), vmax=float(valores.max()),
                caption=var_sel.replace("__", " · "),
            )

            def _style(feature):
                val = feature["properties"].get(var_sel)
                # NaN (no None) para "sin dato": comparar con pd.notna(), no "is not
                # None" -- branca.colormap revienta con NaN ("Thresholds are not sorted").
                color = colormap(val) if pd.notna(val) else "#E3E6EC"
                return {"fillColor": color, "color": "#5B6472", "weight": 0.6, "fillOpacity": 0.8}

            import folium
            layer = folium.GeoJson(
                geo_f, name=var_sel, style_function=_style,
                tooltip=folium.GeoJsonTooltip(
                    fields=["MPIO_CNMBR", "DPTO_CNMBR", var_sel],
                    aliases=["Municipio", "Departamento", var_sel.replace("__", " · ")],
                    sticky=True,
                ),
            )
            layer.add_to(m)
            colormap.add_to(m)
        else:
            st.info("Ningún municipio de la selección tiene dato para esta variable.")
    else:
        valores_unicas = sorted(str(v) for v in df_f[var_sel].dropna().unique())
        paleta = ["#1F3460", "#D7263D", "#F4A83D", "#2E8B57", "#6C3FBF", "#117A8B", "#B7860B"]
        color_map = {v: ui.NIVEL_COLOR.get(v.lower(), paleta[i % len(paleta)]) for i, v in enumerate(valores_unicas)}
        capa_vector_coloreada(
            m, geo_f, color_field=var_sel, color_map=color_map,
            tooltip_fields=["MPIO_CNMBR", "DPTO_CNMBR", var_sel],
            tooltip_aliases=["Municipio", "Departamento", var_sel.replace("__", " · ")],
            nombre=var_sel, color_defecto="#E3E6EC",
        )
        if valores_unicas:
            agregar_leyenda(m, var_sel.replace("__", " · "), [(color_map[v], v) for v in valores_unicas])

    mostrar_mapa(m, key="mapa_cruce_municipal")

with col_tabla:
    cols_mostrar = ["municipio", "departamento", *columnas_cruzadas]
    st.dataframe(
        df_f[cols_mostrar].rename(columns={"municipio": "Municipio", "departamento": "Departamento"}),
        hide_index=True, width="stretch", height=430,
    )

c1, c2 = st.columns(2)
with c1:
    boton_csv(df_f, "cruce_municipal.csv", key="csv_cruce")
with c2:
    boton_geojson(geo_f, "cruce_municipal.geojson", key="geojson_cruce")

# --------------------------------------------------------------------------- #
# Reporte de no-cruce (auditoría, nunca se rellena con estimaciones)
# --------------------------------------------------------------------------- #
with st.expander("📋 Reporte de no-cruce (municipios sin dato, por fuente)"):
    filas_diag = []
    for fid in fuentes_sel:
        cols_fid = [c for c in df.columns if c.startswith(f"{fid}__")]
        if not cols_fid:
            continue
        sin_dato_fid = df[df[cols_fid].isna().all(axis=1)]
        for _, row in sin_dato_fid.iterrows():
            filas_diag.append({
                "divipola": row["divipola"], "municipio": row["municipio"],
                "departamento": row["departamento"], "fuente": fid,
            })
    diag_df = pd.DataFrame(filas_diag)
    if diag_df.empty:
        st.success("Todas las fuentes elegidas cruzan con el universo base de municipios.")
    else:
        st.caption(
            f"{len(diag_df)} combinaciones municipio×fuente sin dato. No se rellenan ni se "
            "estiman: quedan `NaN` en el cruce."
        )
        st.dataframe(diag_df, hide_index=True, width="stretch", height=240)
        DIAG_PATH.parent.mkdir(parents=True, exist_ok=True)
        diag_df.to_csv(DIAG_PATH, index=False, encoding="utf-8-sig")
        boton_csv(diag_df, "divipola_no_cruza.csv", key="csv_diag")

ui.footer()
