"""
pages/4_Pronostico.py
=======================
Pronóstico de corto plazo (ráster: pronóstico 24h, acumulados 24h/72h,
hidroestimador NOAA) y predicción estacional CPT (galería de imágenes por
producto × horizonte, 6 meses).

Las grillas de modelo (WRF/GFS, NetCDF/GeoTIFF/GRIB2) se descargan cuando
publica la fuente pero no siempre están disponibles: se muestran como
"no publicado" (verificado con HEAD) en vez de un error genérico cuando así es.
"""
import re
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import loaders, ui  # noqa: E402
from src.maps import capa_raster, mapa_base, mostrar_mapa  # noqa: E402
from src.downloads import boton_png, boton_generico  # noqa: E402

ui.header(
    "Pronóstico",
    "Pronóstico hidrometeorológico de <b>corto plazo</b> (24–72 h, ráster IDEAM), "
    "predicción <b>estacional CPT</b> (6 meses) y grillas de modelo (WRF/GFS).",
)

tab_corto, tab_estacional, tab_grillas = st.tabs(
    ["🌧️ Corto plazo (ráster)", "📅 Estacional (CPT)", "🧮 Grillas de modelo (WRF/GFS)"]
)

RASTER_DS = [
    ("pronostico_precip_24h", "Pronóstico de precipitación 24h"),
    ("acumulado_24h", "Precipitación acumulada 24h"),
    ("acumulado_72h", "Precipitación acumulada 72h"),
    ("hidroestimador_noaa", "Hidroestimador satelital NOAA"),
]

with tab_corto:
    sel = st.selectbox("Producto ráster", [t for _, t in RASTER_DS])
    ds = next(d for d, t in RASTER_DS if t == sel)
    r = loaders.cargar_raster(ds)
    if r is None:
        ui.sin_datos(ds)
    else:
        png, bounds, legend = r
        opacidad = st.slider("Opacidad", 0.0, 1.0, 0.75, key=f"op_{ds}")
        m = mapa_base()
        capa_raster(m, png, bounds, nombre=sel, opacidad=opacidad)
        mostrar_mapa(m, key=f"mapa_{ds}")
        ui.meta_caption(loaders.metadatos(ds))
        boton_png(png, f"{ds}.png", key=f"png_{ds}")
        if legend:
            with st.expander("Leyenda técnica (JSON de simbología IDEAM)"):
                st.json(legend)

with tab_estacional:
    # Mapeo explícito (no `.lower()`): "Precipitación".lower() conserva la tilde
    # ("precipitación") y no coincide con el dataset real "cpt_prediccion_precipitacion"
    # (sin tilde) -- con .lower() esa pestaña nunca encontraba sus imágenes (bug real,
    # detectado con AppTest: no_publicado se mostraba incluso habiendo snapshot).
    CPT_VARIABLE_A_SUFIJO = {"Precipitación": "precipitacion", "Temperatura": "temperatura", "Viento": "viento"}
    variable = st.radio(
        "Variable", list(CPT_VARIABLE_A_SUFIJO), horizontal=True, key="cpt_var"
    )
    ds = f"cpt_prediccion_{CPT_VARIABLE_A_SUFIJO[variable]}"
    imgs = loaders.cargar_set_imagenes(ds)
    meta = loaders.metadatos(ds)
    if not imgs:
        if meta is not None and meta.get("kind") == "unavailable":
            # el extractor SI verifico con HEAD: esto es "no publicado", no "error"
            ui.no_publicado(meta.get("note", f"El CPT no tiene publicada la variable {variable.lower()} ahora mismo."))
        else:
            ui.sin_datos(ds, "Aún no se ha corrido el extractor para esta variable.")
    else:
        # claves con forma "{PRODUCTO}_mes{N}" (ver ideam_wrf_cpt.fetch_cpt)
        productos = sorted({re.match(r"(.+)_mes\d+", k).group(1) for k in imgs if re.match(r"(.+)_mes\d+", k)})
        prod_sel = st.selectbox("Producto CPT", productos, key="cpt_prod")
        meses_disponibles = sorted(
            int(re.match(rf"{re.escape(prod_sel)}_mes(\d+)", k).group(1))
            for k in imgs if k.startswith(f"{prod_sel}_mes")
        )
        cols = st.columns(min(len(meses_disponibles), 6) or 1)
        for mes, col in zip(meses_disponibles, cols):
            ruta = imgs.get(f"{prod_sel}_mes{mes}")
            with col:
                # No confiar ciegamente en la ruta del manifiesto: si el
                # archivo no existe (snapshot incompleto, ruta rota), no
                # tumbar la página con MediaFileStorageError.
                if ruta and Path(ruta).exists():
                    st.image(ruta, caption=f"Mes {mes}", width="stretch")
                    boton_png(ruta, f"{ds}_{prod_sel}_mes{mes}.png", key=f"png_{ds}_{prod_sel}_{mes}")
                else:
                    st.caption(f"Mes {mes}: imagen no disponible.")
        ui.meta_caption(meta)

with tab_grillas:
    GRID_DS = [
        ("wrf00_netcdf", "WRF 00Z Colombia (NetCDF)"),
        ("wrf00_tif", "WRF 00Z Colombia (GeoTIFF)"),
        ("gfs06_grib2", "GFS 06Z Colombia (GRIB2)"),
    ]
    st.caption(
        "Grillas crudas de modelo, para procesar con xarray/cfgrib/rasterio. No se "
        "visualizan en el navegador (son datos multibanda), sólo se descargan."
    )
    for ds, titulo in GRID_DS:
        meta = loaders.metadatos(ds)
        with st.expander(titulo):
            if meta is None:
                ui.sin_datos(ds, "Puede que la corrida más reciente aún no publique esta grilla.")
                continue
            files = meta.get("files", {})
            ruta_data = files.get("data")
            # Path("").exists() da True (se resuelve como '.'): sin el chequeo
            # de cadena vacía, un manifiesto sin la clave "data" intentaría
            # leer el directorio actual como si fuera un archivo.
            p = Path(ruta_data) if ruta_data else None
            ui.meta_caption(meta)
            if p is not None and p.exists():
                boton_generico(
                    p.read_bytes(), p.name, "application/octet-stream",
                    f"⬇️ Descargar {p.name} ({meta.get('size_bytes', 0) / 1e6:.1f} MB)",
                    key=f"grid_{ds}",
                )
            else:
                ui.sin_datos(ds)

ui.footer()
