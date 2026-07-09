"""
pages/2_Alertas.py
====================
Consulta de datos diarios del árbol /ospa/Alertas/ de IDEAM (BART),
materializado por bart_alertas.py: descensos de temperatura, granizo, índice
de calor, temperaturas municipales, datos diarios preliminares,
hidroestimador satelital y los modelos de amenaza (deslizamientos,
incendios, hidrología).

Cada categoría organizada por fecha sólo guarda la fecha más reciente con
datos (no el histórico completo): es consulta de "hoy", no un archivo
histórico. Los rásters de muy alta resolución (>60MB) se omiten de forma
auditable — ver el manifiesto de cada dataset ('omitidos').
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import loaders, ui  # noqa: E402
from src.maps import mapa_base, mostrar_mapa, capa_vector_coloreada, agregar_leyenda  # noqa: E402
from src.downloads import boton_csv, boton_generico, boton_geojson  # noqa: E402

ui.header(
    "Alertas (datos diarios)",
    "Datos diarios del árbol <b>/ospa/Alertas/</b> de IDEAM: descensos de temperatura, "
    "granizo, índice de calor, temperaturas municipales y los modelos de amenaza "
    "(deslizamientos, incendios, hidrología). Sólo se consulta la fecha más reciente "
    "con datos publicados.",
)


def _agrupar_por_subcarpeta(files: dict) -> dict[str, dict[str, str]]:
    grupos: dict[str, dict[str, str]] = {}
    for clave, ruta in files.items():
        if "/" in clave:
            sub, nombre = clave.split("/", 1)
        else:
            sub, nombre = "archivo", clave
        grupos.setdefault(sub, {})[nombre] = ruta
    return grupos


def _render_categoria_por_fecha(dataset: str, titulo_col_tabla: str = "csv") -> None:
    meta = loaders.cargar_alerta(dataset)
    if meta is None:
        ui.sin_datos(dataset)
        return
    st.caption(f"Fecha de los datos: **{meta.get('fecha', '—')}**")
    ui.meta_caption(meta)
    if meta.get("omitidos"):
        with st.expander(f"⚠️ {len(meta['omitidos'])} archivo(s) omitido(s) por tamaño"):
            st.caption("Rásters de muy alta resolución no se replican en el repositorio. Enlace de origen:")
            for o in meta["omitidos"]:
                st.markdown(f"- `{o['archivo']}` → [{o['url']}]({o['url']})")

    grupos = _agrupar_por_subcarpeta(meta.get("files", {}))

    # Tablas (csv/excel)
    for sub in (titulo_col_tabla, "excel"):
        if sub not in grupos:
            continue
        for nombre, ruta in grupos[sub].items():
            p = Path(ruta)
            if not p.exists():
                continue
            try:
                df = pd.read_csv(p) if p.suffix.lower() == ".csv" else pd.read_excel(p)
                st.markdown(f"**{nombre}**")
                st.dataframe(df, hide_index=True, width="stretch", height=300)
                boton_csv(df, f"{p.stem}.csv", key=f"csv_{dataset}_{nombre}")
            except Exception:  # noqa: BLE001
                boton_generico(p.read_bytes(), p.name, "application/octet-stream",
                                f"⬇️ {nombre}", key=f"gen_{dataset}_{nombre}")

    # Mapas (imágenes)
    if "mapas" in grupos:
        st.markdown("**Mapas**")
        cols = st.columns(min(len(grupos["mapas"]), 3) or 1)
        for i, (nombre, ruta) in enumerate(grupos["mapas"].items()):
            p = Path(ruta)
            if p.exists():
                with cols[i % len(cols)]:
                    st.image(str(p), caption=nombre, width="stretch")

    # Todo lo demás (shape, raster, txt): sólo descarga
    otros = {k: v for k, v in grupos.items() if k not in (titulo_col_tabla, "excel", "mapas")}
    if otros:
        with st.expander("Otros archivos (shapefile / ráster / texto) — descarga"):
            for sub, archivos in otros.items():
                for nombre, ruta in archivos.items():
                    p = Path(ruta)
                    if p.exists():
                        boton_generico(p.read_bytes(), p.name, "application/octet-stream",
                                        f"⬇️ {sub}/{nombre}", key=f"otro_{dataset}_{sub}_{nombre}")


def _render_temperatura_municipal(tipo: str) -> None:
    dataset = f"temp_{tipo}_municipios"
    meta = loaders.cargar_alerta(dataset)
    if meta is None:
        ui.sin_datos(dataset)
        return
    df = loaders.cargar_temperatura_municipal(tipo)
    if df is None or df.empty:
        ui.sin_datos(dataset, "El CSV municipal no tiene las columnas esperadas.")
        return
    st.caption(f"Fecha de los datos: **{meta.get('fecha', '—')}**")
    ui.kpi_row([
        {"label": "Municipios con dato", "value": str(df["TEMPERATURA"].notna().sum()), "icon": "🌡️"},
        {"label": "Promedio (°C)", "value": f"{df['TEMPERATURA'].mean():.1f}", "icon": "📊"},
        {"label": "Máximo" if tipo == "max" else "Mínimo", "value": f"{df['TEMPERATURA'].max() if tipo=='max' else df['TEMPERATURA'].min():.1f} °C", "icon": "🔺" if tipo == "max" else "🔻"},
    ])
    base, geo_base = loaders.cargar_base_municipal()
    df_join = base.merge(df.rename(columns={"COD_DANE": "divipola"}), on="divipola", how="left")
    df_join["divipola"] = df_join["divipola"].astype(str).str.zfill(5)

    col_map, col_tabla = st.columns([3, 2])
    with col_map:
        import branca.colormap as cmlib
        import folium
        valores = df_join["TEMPERATURA"].dropna()
        if len(valores) > 0:
            colormap = cmlib.LinearColormap(
                colors=["#1F6FEB", "#F4A83D", "#D7263D"] if tipo == "max" else ["#5B6472", "#1F6FEB", "#E7F0FA"],
                vmin=float(valores.min()), vmax=float(valores.max()), caption="Temperatura (°C)",
            )
            temp_by_cod = dict(zip(df_join["divipola"], df_join["TEMPERATURA"]))
            geo_f = {
                "type": "FeatureCollection",
                "features": [f for f in geo_base["features"]
                              if str(f["properties"].get("MPIO_CCNCT", "")).strip().zfill(5) in temp_by_cod],
            }

            def _style(feature):
                cod = str(feature["properties"].get("MPIO_CCNCT", "")).strip().zfill(5)
                val = temp_by_cod.get(cod)
                # OJO: un municipio sin dato queda como NaN (float), no None -- si no se
                # filtra con pd.notna(), branca.colormap revienta ("Thresholds are not
                # sorted") porque las comparaciones con NaN nunca son verdaderas.
                return {"fillColor": colormap(val) if pd.notna(val) else "#E3E6EC",
                        "color": "#5B6472", "weight": 0.5, "fillOpacity": 0.8}

            m = mapa_base()
            folium.GeoJson(geo_f, style_function=_style).add_to(m)
            colormap.add_to(m)
            mostrar_mapa(m, key=f"mapa_temp_{tipo}")
        else:
            st.info("Sin datos numéricos para mapear.")
    with col_tabla:
        st.dataframe(
            df_join[["municipio", "departamento", "TEMPERATURA"]].rename(
                columns={"municipio": "Municipio", "departamento": "Departamento", "TEMPERATURA": "Temperatura (°C)"}
            ).sort_values("Temperatura (°C)", ascending=(tipo != "max")),
            hide_index=True, width="stretch", height=430,
        )
    boton_csv(df, f"{dataset}.csv", key=f"csv_{dataset}")
    ui.meta_caption(meta)


def _render_amenaza_modelo(categoria: str, titulo: str) -> None:
    dataset = f"amenaza_{categoria}"
    meta = loaders.cargar_alerta(dataset)
    if meta is None:
        ui.sin_datos(dataset)
        return
    df = loaders.cargar_amenaza_modelo(categoria)
    if df is None or df.empty:
        ui.sin_datos(dataset, "El CSV del modelo no tiene las columnas esperadas.")
        return
    conteo = df["TEXTO_AMENAZA"].value_counts()
    ui.kpi_row([
        {"label": f"Municipios evaluados ({titulo})", "value": str(len(df)), "icon": "🏘️"},
        *[{"label": nivel, "value": str(n), "icon": "🔴" if nivel.upper() == "ALTA" else "🟡" if nivel.upper() == "MEDIA" else "🟢"}
          for nivel, n in conteo.items()],
    ])
    base, geo_base = loaders.cargar_base_municipal()
    df["COD_DANE"] = df["COD_DANE"].astype(str).str.zfill(5)
    amenaza_by_cod = dict(zip(df["COD_DANE"], df["TEXTO_AMENAZA"]))
    geo_f = {
        "type": "FeatureCollection",
        "features": [f for f in geo_base["features"]
                      if str(f["properties"].get("MPIO_CCNCT", "")).strip().zfill(5) in amenaza_by_cod],
    }
    niveles = sorted(df["TEXTO_AMENAZA"].dropna().unique())
    color_map = {n: ui.NIVEL_COLOR.get(n.lower(), "#7A7F87") for n in niveles}

    col_map, col_tabla = st.columns([3, 2])
    with col_map:
        m = mapa_base()
        # inyecta el nivel de amenaza como propiedad de cada feature para el color/tooltip
        for f in geo_f["features"]:
            cod = str(f["properties"].get("MPIO_CCNCT", "")).strip().zfill(5)
            f["properties"]["_amenaza"] = amenaza_by_cod.get(cod)
        capa_vector_coloreada(
            m, geo_f, color_field="_amenaza", color_map=color_map,
            tooltip_fields=["MPIO_CNMBR", "DPTO_CNMBR", "_amenaza"],
            tooltip_aliases=["Municipio", "Departamento", "Amenaza"], nombre=titulo,
        )
        if niveles:
            agregar_leyenda(m, "Nivel de amenaza", [(color_map[n], n) for n in niveles])
        mostrar_mapa(m, key=f"mapa_{dataset}")
    with col_tabla:
        base_nombres = base.rename(columns={"divipola": "COD_DANE"})[["COD_DANE", "municipio", "departamento"]]
        tabla = base_nombres.merge(df, on="COD_DANE", how="right")
        st.dataframe(
            tabla.rename(columns={"municipio": "Municipio", "departamento": "Departamento", "TEXTO_AMENAZA": "Amenaza"}),
            hide_index=True, width="stretch", height=430,
        )
    boton_csv(df, f"{dataset}.csv", key=f"csv_{dataset}")
    ui.meta_caption(meta)


def _render_amenaza_hidrologia() -> None:
    dataset = "amenaza_hidrologia"
    meta = loaders.cargar_alerta(dataset)
    if meta is None:
        ui.sin_datos(dataset)
        return
    files = meta.get("files", {})
    geojson_path = files.get("geojson")
    if geojson_path and Path(geojson_path).exists():
        import json
        geo = json.loads(Path(geojson_path).read_text(encoding="utf-8"))
        st.caption(f"{len(geo.get('features', []))} zonas con alerta hidrológica vigente")
        m = mapa_base()
        capa_vector_coloreada(
            m, geo, color_field="TEXTO_ALERT" if geo["features"] and "TEXTO_ALERT" in geo["features"][0]["properties"] else "",
            color_map={}, tooltip_fields=list(geo["features"][0]["properties"].keys())[:5] if geo["features"] else [],
            nombre=dataset,
        )
        mostrar_mapa(m, key="mapa_amenaza_hidrologia")
        boton_geojson(geo, "amenaza_hidrologia.geojson", key="geojson_hidrologia")
    else:
        st.info("Shapefile disponible sólo para descarga (sin conversión a GeoJSON).")
    for nombre, ruta in files.items():
        p = Path(ruta)
        if p.exists() and p.suffix.lower() in (".shp", ".shx", ".dbf", ".prj"):
            boton_generico(p.read_bytes(), p.name, "application/octet-stream",
                            f"⬇️ {p.name}", key=f"shp_{nombre}")
    ui.meta_caption(meta)


def _render_flat(dataset: str) -> None:
    meta = loaders.cargar_alerta(dataset)
    if meta is None:
        ui.sin_datos(dataset)
        return
    ui.meta_caption(meta)
    if meta.get("omitidos"):
        st.caption(f"⚠️ {len(meta['omitidos'])} archivo(s) omitido(s) por tamaño (ver manifiesto).")
    files = meta.get("files", {})
    st.caption(f"{len(files)} archivo(s) disponibles")
    for nombre, ruta in sorted(files.items()):
        p = Path(ruta)
        if p.exists():
            if p.suffix.lower() in (".png", ".jpg", ".jpeg"):
                st.image(str(p), caption=nombre, width="stretch")
            boton_generico(p.read_bytes(), p.name, "application/octet-stream",
                            f"⬇️ {nombre}", key=f"flat_{dataset}_{nombre}")


tabs = st.tabs([
    "🌡️ Descensos de temperatura", "🧊 Granizo", "🔥 Índice de calor",
    "🌡️ Temp. municipal", "📋 Diarios preliminares", "🛰️ Hidroestimador",
    "⚠️ Amenaza (modelos)",
])

with tabs[0]:
    _render_categoria_por_fecha("descensos_temperatura")
with tabs[1]:
    _render_categoria_por_fecha("granizo")
with tabs[2]:
    _render_categoria_por_fecha("indice_calor")
with tabs[3]:
    sub = st.radio("Variable", ["Máxima", "Mínima"], horizontal=True, key="sub_temp_muni")
    _render_temperatura_municipal("max" if sub == "Máxima" else "min")
with tabs[4]:
    _render_flat("datos_diarios_preliminares")
with tabs[5]:
    _render_flat("hidroestimador_satelital")
with tabs[6]:
    sub2 = st.radio(
        "Modelo", ["Deslizamientos", "Incendios", "Hidrología"], horizontal=True, key="sub_amenaza_modelo",
    )
    if sub2 == "Deslizamientos":
        _render_amenaza_modelo("deslizamientos", "Amenaza por deslizamientos")
    elif sub2 == "Incendios":
        _render_amenaza_modelo("incendios", "Amenaza por incendios")
    else:
        _render_amenaza_hidrologia()

ui.footer()
