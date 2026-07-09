"""
cruce_divipola.py
==================
Motor de cruce de datos municipales por código DIVIPOLA (5 dígitos). Es el
núcleo de la página "Consulta y cruce municipal": toma como universo base
los 1.122 municipios de la capa de índices de riesgo SNGRD (única fuente con
geometría de polígono utilizable para mapa coroplético) y le hace left-join
a las demás fuentes que el usuario elija, todas normalizadas a código
DIVIPOLA string de 5 dígitos (zfill(5)).

No inventa cruces: un municipio ausente en una fuente queda con NaN en las
columnas de esa fuente (no se rellena con estimaciones). El reporte de
discrepancias de código completo vive en scripts/diagnostico_divipola.py.

Uso desde la app:
    import cruce_divipola as cd
    base, geo_base = cd.cargar_base_municipal()
    df = cd.cruzar(["sala_crisis", "temp_max_municipal"])
    geo = cd.geojson_con_atributos(df, geo_base)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent
REFERENCIA_RIESGO = ROOT / "data" / "reference" / "indices_riesgo_municipal.geojson"

CODE_FIELD_RIESGO = "MPIO_CCNCT"
NOMBRE_FIELD_RIESGO = "MPIO_CNMBR"
DPTO_FIELD_RIESGO = "DPTO_CNMBR"


def normalizar_codigo(serie: pd.Series) -> pd.Series:
    """DIVIPOLA a string de 5 dígitos, tolerante a floats/enteros (Socrata,
    Excel y CSV suelen perder el cero a la izquierda o traer '5001.0')."""
    return (
        serie.astype(str).str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(5)
    )


def cargar_base_municipal() -> tuple[pd.DataFrame, dict]:
    """Universo base: 1.122 municipios de la capa de riesgo SNGRD (única con
    geometría de polígono). Devuelve (DataFrame de atributos, GeoJSON dict)."""
    geo = json.loads(REFERENCIA_RIESGO.read_text(encoding="utf-8"))
    filas = []
    for f in geo["features"]:
        p = f["properties"]
        filas.append({
            "divipola": p.get(CODE_FIELD_RIESGO),
            "municipio": p.get(NOMBRE_FIELD_RIESGO),
            "departamento": p.get(DPTO_FIELD_RIESGO),
        })
    df = pd.DataFrame(filas)
    df["divipola"] = normalizar_codigo(df["divipola"])
    return df, geo


# --------------------------------------------------------------------------- #
# Registro de fuentes cruzables
# --------------------------------------------------------------------------- #
FUENTES: dict[str, dict] = {}


def registrar_fuente(id_: str, nombre: str, loader: Callable[[], Optional[pd.DataFrame]],
                      col_codigo: str, columnas: list[str], descripcion: str) -> None:
    FUENTES[id_] = {
        "nombre": nombre, "loader": loader, "col_codigo": col_codigo,
        "columnas": columnas, "descripcion": descripcion,
    }


def _registrar_fuentes_estandar() -> None:
    """Registra las fuentes que la app ya sabe cargar. Imports perezosos para
    no acoplar módulos innecesariamente al importar cruce_divipola."""
    import sala_crisis as sc
    import dane_terridata as dane

    def _sala_crisis_agg():
        df = sc.agregados_por_municipio()
        return df.rename(columns={"Codigo Municipio": "_cod"})

    registrar_fuente(
        "sala_crisis", "Sala de Crisis (emergencias históricas)", _sala_crisis_agg,
        "_cod", ["n_emergencias", "familias", "personas", "muertos"],
        "Conteo y afectación histórica acumulada, todas las épocas y tipos de evento.",
    )

    def _dane_car():
        df = dane.load_caracterizacion()
        if df is None:
            return None
        return df.rename(columns={"mpio_codigo": "_cod"})

    registrar_fuente(
        "dane", "DANE (DIVIPOLA + caracterización)", _dane_car,
        "_cod", ["total_hogares", "pct_rural", "pct_indigena", "pct_narp_afro",
                 "pct_rrom", "pct_raizal", "pct_palenquero", "estrato_predominante"],
        "DIVIPOLA verificada (nombres/coords); hogares/rural/etnia/estrato PENDIENTES "
        "de fuente nacional verificada (columnas presentes pero vacías, no inventadas).",
    )

    try:
        import bart_alertas as ba
    except ModuleNotFoundError:
        ba = None
    if ba is not None:
        registrar_fuente(
            "temp_max_municipal", "Temperatura máxima municipal (BART, diaria)",
            lambda: ba.load_temperatura_municipal("max"),
            "COD_DANE", ["TEMPERATURA"], "Última corrida diaria de IDEAM/BART.",
        )
        registrar_fuente(
            "temp_min_municipal", "Temperatura mínima municipal (BART, diaria)",
            lambda: ba.load_temperatura_municipal("min"),
            "COD_DANE", ["TEMPERATURA"], "Última corrida diaria de IDEAM/BART.",
        )
        registrar_fuente(
            "amenaza_deslizamientos", "Amenaza por deslizamientos (modelo BART, diaria)",
            lambda: ba.load_amenaza_modelo("deslizamientos"),
            "COD_DANE", ["TEXTO_AMENAZA"], "Última corrida diaria del modelo de deslizamientos IDEAM.",
        )
        registrar_fuente(
            "amenaza_incendios", "Amenaza por incendios (modelo BART, diaria)",
            lambda: ba.load_amenaza_modelo("incendios"),
            "COD_DANE", ["TEXTO_AMENAZA"], "Última corrida diaria del modelo de incendios IDEAM.",
        )


_registrar_fuentes_estandar()


def cruzar(fuentes_ids: list[str], base: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Left-join de las fuentes elegidas sobre el universo base municipal, por
    DIVIPOLA. Fuentes sin snapshot o sin dato para un municipio quedan NaN."""
    if base is None:
        base, _ = cargar_base_municipal()
    out = base.copy()
    for fid in fuentes_ids:
        meta = FUENTES.get(fid)
        if meta is None:
            continue
        df = meta["loader"]()
        prefijo_cols = [f"{fid}__{c}" for c in meta["columnas"]]
        if df is None or len(df) == 0:
            for col in prefijo_cols:
                out[col] = pd.NA
            continue
        df = df.copy()
        df["_join"] = normalizar_codigo(df[meta["col_codigo"]])
        cols_presentes = [c for c in meta["columnas"] if c in df.columns]
        agg = df.groupby("_join")[cols_presentes].first().reset_index()
        agg = agg.rename(columns={c: f"{fid}__{c}" for c in cols_presentes})
        out = out.merge(agg, left_on="divipola", right_on="_join", how="left")
        if "_join" in out.columns:
            out = out.drop(columns="_join")
    return out


def geojson_con_atributos(df_cruzado: pd.DataFrame, geo_base: Optional[dict] = None) -> dict:
    """Reconstruye un GeoJSON con las columnas cruzadas en las properties de
    cada municipio, para mapa y descarga."""
    if geo_base is None:
        _, geo_base = cargar_base_municipal()
    df_cruzado = df_cruzado.set_index("divipola")
    out = {"type": "FeatureCollection", "features": []}
    for f in geo_base["features"]:
        cod = normalizar_codigo(pd.Series([f["properties"].get(CODE_FIELD_RIESGO)])).iloc[0]
        props = dict(f["properties"])
        if cod in df_cruzado.index:
            fila = df_cruzado.loc[cod]
            if isinstance(fila, pd.DataFrame):  # por si hay codigos duplicados
                fila = fila.iloc[0]
            props.update({k: v for k, v in fila.to_dict().items()
                          if k not in ("municipio", "departamento")})
        out["features"].append({"type": "Feature", "properties": props, "geometry": f["geometry"]})
    return out
