"""
src/loaders.py
===============
Único punto donde la app toca los scripts extractores. Son wrappers finos,
cacheados con @st.cache_data, sobre las funciones load_*/latest_meta ya
definidas en ideam_extractor.py, ideam_wrf_cpt.py, bart_alertas.py,
dane_terridata.py, sala_crisis.py y cruce_divipola.py.

No se reimplementa nada de la lógica de lectura de snapshots: solo se
importa y se envuelve. La app NUNCA llama a IDEAM/DANE en vivo: todo pasa
por el patrón data_lake/{dataset}/latest.json que producen los scripts
(vía cron de GitHub Actions).

Si un dataset aún no tiene snapshot (FileNotFoundError), las funciones
devuelven None en vez de reventar: la página debe mostrarlo con gracia.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

# Los scripts extractores viven en la raíz del repo.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ideam_extractor as _ext  # noqa: E402

TTL = 3600  # 1 hora: coherente con la cadencia del cron de ingesta

REFERENCIA_INDICES_RIESGO = ROOT / "data" / "reference" / "indices_riesgo_municipal.geojson"


@st.cache_data(ttl=TTL, show_spinner=False)
def cargar_referencia_indices_riesgo() -> Optional[dict]:
    """Capa estática de referencia (1.122 municipios, índices SNGRD), ya
    simplificada geométricamente (ver scripts/simplificar_indices_riesgo.py).
    No es un snapshot de data_lake: es el universo base del cruce municipal
    (única fuente con geometría de polígono utilizable para mapa coroplético)."""
    import json
    if not REFERENCIA_INDICES_RIESGO.exists():
        return None
    return json.loads(REFERENCIA_INDICES_RIESGO.read_text(encoding="utf-8"))


def _safe(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except FileNotFoundError:
        return None


# --------------------------------------------------------------------------- #
# Sala de Crisis (emergencias históricas) y DANE-DIVIPOLA (caracterización)
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=TTL, show_spinner=False)
def cargar_emergencias() -> Optional[pd.DataFrame]:
    import sala_crisis as _sc
    return _safe(_sc.load_emergencias)


@st.cache_data(ttl=TTL, show_spinner=False)
def cargar_recurrencia_municipio_evento() -> Optional[pd.DataFrame]:
    import sala_crisis as _sc
    return _safe(_sc.recurrencia_por_municipio_evento)


@st.cache_data(ttl=TTL, show_spinner=False)
def cargar_eventos_por_departamento() -> Optional[pd.DataFrame]:
    import sala_crisis as _sc
    return _safe(_sc.eventos_por_departamento)


@st.cache_data(ttl=TTL, show_spinner=False)
def cargar_caracterizacion_dane() -> Optional[pd.DataFrame]:
    import dane_terridata as _dane
    return _safe(_dane.load_caracterizacion)


# --------------------------------------------------------------------------- #
# Alertas BART (bart_alertas.py) — categorías materializadas del árbol
# /ospa/Alertas/, cada una identificada por su dataset_id de data_lake/.
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=TTL, show_spinner=False)
def cargar_alerta(dataset: str) -> Optional[dict]:
    """Manifiesto (latest.json) de cualquier categoría de Alertas materializada."""
    import bart_alertas as _ba
    return _safe(_ba.load_alerta, dataset)


@st.cache_data(ttl=TTL, show_spinner=False)
def cargar_temperatura_municipal(tipo: str) -> Optional[pd.DataFrame]:
    import bart_alertas as _ba
    return _safe(_ba.load_temperatura_municipal, tipo)


@st.cache_data(ttl=TTL, show_spinner=False)
def cargar_amenaza_modelo(categoria: str) -> Optional[pd.DataFrame]:
    import bart_alertas as _ba
    return _safe(_ba.load_amenaza_modelo, categoria)


# --------------------------------------------------------------------------- #
# Cruce municipal DIVIPOLA (cruce_divipola.py) — núcleo del portal
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=TTL, show_spinner=False)
def fuentes_cruzables() -> dict[str, dict]:
    """{id_fuente: {nombre, columnas, descripcion}} — sin el loader (no es
    serializable de forma estable para el caché de Streamlit)."""
    import cruce_divipola as _cd
    return {
        fid: {"nombre": m["nombre"], "columnas": m["columnas"], "descripcion": m["descripcion"]}
        for fid, m in _cd.FUENTES.items()
    }


@st.cache_data(ttl=TTL, show_spinner=False)
def cargar_base_municipal() -> tuple[pd.DataFrame, dict]:
    import cruce_divipola as _cd
    return _cd.cargar_base_municipal()


@st.cache_data(ttl=TTL, show_spinner=False)
def cruzar_fuentes(fuentes_ids: tuple[str, ...]) -> pd.DataFrame:
    """cruce_divipola.cruzar(), cacheado. fuentes_ids debe ser tupla (hashable)
    para que @st.cache_data pueda usarla como clave."""
    import cruce_divipola as _cd
    return _cd.cruzar(list(fuentes_ids))


def geojson_con_atributos(df_cruzado: pd.DataFrame, geo_base: Optional[dict] = None) -> dict:
    # No cacheado: recibe un DataFrame ya cruzado (típicamente filtrado en la
    # UI), armar la clave de caché sería más caro que recomputar el join.
    import cruce_divipola as _cd
    return _cd.geojson_con_atributos(df_cruzado, geo_base)


# --------------------------------------------------------------------------- #
# Catálogo: dataset_id -> (nombre visible, tipo, descripción corta)
# --------------------------------------------------------------------------- #
CATALOGO = {
    # Vectoriales (ArcGIS OSPA)
    "precipitacion_diaria":   ("Precipitación diaria por estación", "puntos", "IDEAM (ArcGIS OSPA)"),
    "temperatura_max_diaria": ("Temperatura máxima diaria por estación", "puntos", "IDEAM (ArcGIS OSPA)"),
    "alertas_hidrologicas":   ("Alertas hidrológicas vigentes", "poligonos", "IDEAM (ArcGIS OSPA)"),
    "areas_hidrograficas":    ("Áreas hidrográficas (referencia)", "poligonos", "IDEAM (ArcGIS OSPA)"),
    "zonas_hidrograficas":    ("Zonas hidrográficas (referencia)", "poligonos", "IDEAM (ArcGIS OSPA)"),
    "alertas_idd":            ("Alertas por deslizamientos (municipio)", "poligonos", "IDEAM (ArcGIS OSPA)"),
    "alertas_icv":            ("Alertas por incendios de cobertura vegetal", "poligonos", "IDEAM (ArcGIS OSPA)"),
    "amenaza_idd":            ("Amenaza por deslizamientos (ráster ArcGIS)", "raster", "IDEAM (ArcGIS OSPA)"),
    "amenaza_icv":            ("Amenaza por incendios (ráster ArcGIS)", "raster", "IDEAM (ArcGIS OSPA)"),
    "municipios":              ("Municipios (referencia)", "poligonos", "IDEAM (ArcGIS OSPA)"),
    "departamentos":           ("Departamentos e islas (referencia)", "poligonos", "IDEAM (ArcGIS OSPA)"),
    # Ráster (ArcGIS OSPA)
    "pronostico_precip_24h":  ("Pronóstico de precipitación 24h", "raster", "IDEAM (ArcGIS OSPA)"),
    "acumulado_24h":          ("Precipitación acumulada 24h", "raster", "IDEAM (ArcGIS OSPA)"),
    "acumulado_72h":          ("Precipitación acumulada 72h", "raster", "IDEAM (ArcGIS OSPA)"),
    "hidroestimador_noaa":    ("Hidroestimador satelital NOAA (ArcGIS)", "raster", "IDEAM / NOAA"),
    # Modelos grillados y predicción estacional
    "wrf00_netcdf":           ("WRF 00Z Colombia (NetCDF)", "grid", "IDEAM"),
    "wrf00_tif":              ("WRF 00Z Colombia (GeoTIFF)", "grid", "IDEAM"),
    "gfs06_grib2":            ("GFS 06Z Colombia (GRIB2)", "grid", "IDEAM / NOAA"),
    "cpt_prediccion_precipitacion": ("Predicción mensual CPT — Precipitación", "image_set", "IDEAM"),
    "cpt_prediccion_temperatura":   ("Predicción mensual CPT — Temperatura", "image_set", "IDEAM"),
    "cpt_prediccion_viento":        ("Predicción mensual CPT — Viento", "image_set", "IDEAM"),
    # Alertas BART (/ospa/Alertas/, bart_alertas.py)
    "descensos_temperatura":  ("Descensos de temperatura (última fecha)", "alerta_diaria", "IDEAM (BART)"),
    "granizo":                 ("Granizo (última fecha)", "alerta_diaria", "IDEAM (BART)"),
    "indice_calor":            ("Índice de calor (última fecha)", "alerta_diaria", "IDEAM (BART)"),
    "temp_max_municipios":     ("Temperatura máxima municipal (última fecha)", "alerta_diaria", "IDEAM (BART)"),
    "temp_min_municipios":     ("Temperatura mínima municipal (última fecha)", "alerta_diaria", "IDEAM (BART)"),
    "datos_diarios_preliminares": ("Reportes diarios preliminares", "alerta_diaria", "IDEAM (BART)"),
    "hidroestimador_satelital":   ("Hidroestimador satelital (rásters recientes)", "alerta_diaria", "IDEAM (BART)"),
    "amenaza_deslizamientos":  ("Amenaza por deslizamientos (modelo, última corrida)", "amenaza_modelo", "IDEAM (BART)"),
    "amenaza_incendios":       ("Amenaza por incendios (modelo, última corrida)", "amenaza_modelo", "IDEAM (BART)"),
    "amenaza_hidrologia":      ("Alertas hidrológicas vigentes (modelo)", "vector", "IDEAM (BART)"),
    # Caracterización municipal
    "dane_divipola":           ("DIVIPOLA oficial (nombres/coordenadas de municipio)", "tabla", "DANE"),
}


@st.cache_data(ttl=TTL, show_spinner=False)
def dataset_disponible(dataset: str) -> bool:
    return _safe(_ext.latest_meta, dataset) is not None


@st.cache_data(ttl=TTL, show_spinner=False)
def cargar_geojson(dataset: str) -> Optional[dict]:
    return _safe(_ext.load_latest_geojson, dataset)


@st.cache_data(ttl=TTL, show_spinner=False)
def cargar_tabla(dataset: str) -> Optional[pd.DataFrame]:
    return _safe(_ext.load_latest_table, dataset)


@st.cache_data(ttl=TTL, show_spinner=False)
def cargar_tabla_con_respaldo_xlsx(dataset: str) -> tuple[Optional[pd.DataFrame], Optional[str]]:
    """Como cargar_tabla, pero si el parquet no existe (Excel con tipos mixtos que
    el extractor no pudo tabular), intenta una lectura tolerante del .xlsx crudo
    para al menos mostrarlo en pantalla. Devuelve (df_o_None, ruta_xlsx_o_None)."""
    df = cargar_tabla(dataset)
    m = metadatos(dataset)
    ruta_xlsx = m["files"].get("xlsx") if m else None
    if df is not None:
        return df, ruta_xlsx
    if ruta_xlsx:
        try:
            df = pd.read_excel(ruta_xlsx, engine="openpyxl", dtype=str)
        except Exception:  # noqa: BLE001
            df = None
    return df, ruta_xlsx


@st.cache_data(ttl=TTL, show_spinner=False)
def cargar_raster(dataset: str):
    """(ruta_png:str, bounds:list, leyenda:dict) o None si no hay snapshot."""
    r = _safe(_ext.load_latest_raster, dataset)
    if r is None:
        return None
    png, bounds, legend = r
    return str(png), bounds, legend


@st.cache_data(ttl=TTL, show_spinner=False)
def metadatos(dataset: str) -> Optional[dict]:
    return _safe(_ext.latest_meta, dataset)


@st.cache_data(ttl=TTL, show_spinner=False)
def datasets_disponibles() -> list[str]:
    return _ext.list_datasets()


@st.cache_data(ttl=TTL, show_spinner=False)
def cargar_set_imagenes(dataset: str) -> Optional[dict]:
    """Para datasets tipo image_set (CPT): {clave: ruta_png} desde el manifiesto."""
    m = metadatos(dataset)
    if m is None:
        return None
    return {k: v for k, v in m.get("files", {}).items()}
