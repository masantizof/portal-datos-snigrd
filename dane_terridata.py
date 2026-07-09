"""
dane_terridata.py
===================
Caracterización municipal (DIVIPOLA oficial DANE). Reutiliza el patrón del
extractor base (sesión, dedup, latest.json).

IMPORTANTE — decisión documentada, no un accidente:
La API Socrata de TerriData (`64cq-xb2k`) mencionada en versiones previas
del requerimiento devuelve 404 (dataset dado de baja/migrado); tampoco se
encontró en datos.gov.co un dataset Socrata de cobertura NACIONAL para
hogares/ruralidad/etnia/estrato (lo que existe está fragmentado por
municipio individual). Probar URLs adivinadas del Geoportal DANE (rutas de
CNPV 2018) devolvió 404. Por la regla dura del requerimiento ("ninguna URL
entra sin HEAD/GET 200 y cobertura ≥1.100 municipios"), estos campos NO se
inventan: quedan como columnas presentes pero vacías, con
`PENDIENTE_FUENTE = True` documentado, hasta que se provea el archivo o
enlace correcto.

Lo único verificado y en uso hoy es la DIVIPOLA oficial (nombres de
municipio/departamento, coordenadas) — 1.122 municipios, HEAD/GET 200:
    https://geoportal.dane.gov.co/descargas/divipola/DIVIPOLA_Municipios.xlsx

Uso desde la app:
    from dane_terridata import load_caracterizacion, enriquecer, CAMPOS_PENDIENTES
    car = load_caracterizacion()
    df2 = enriquecer(df, cod_col="MPIO_CCNCT")
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ideam_extractor import (  # noqa: E402
    SESSION, DATA_ROOT, TIMEOUT, log,
    _sha256, _partition_dir, _changed, _commit_hash,
    _write_manifest, _maybe_upload_oss,
)

DIVIPOLA_URL = "https://geoportal.dane.gov.co/descargas/divipola/DIVIPOLA_Municipios.xlsx"
DATASET = "dane_divipola"

# Campos que el requerimiento pide (hogares, % rural, % étnico, % estrato)
# pero para los que NO hay fuente nacional verificada todavía. Se exponen
# como columnas con valor nulo, no se omiten, para que enriquecer() no
# rompa el join y la UI pueda mostrar "sin dato (fuente pendiente)".
CAMPOS_PENDIENTES = [
    "total_hogares", "pct_rural", "pct_indigena", "pct_narp_afro",
    "pct_rrom", "pct_raizal", "pct_palenquero", "estrato_predominante",
]


def fetch_divipola() -> bool:
    """Descarga la DIVIPOLA oficial (nombres/coordenadas de municipio). Devuelve
    True si escribió un snapshot nuevo."""
    r = SESSION.get(DIVIPOLA_URL, timeout=TIMEOUT)
    r.raise_for_status()
    raw = r.content
    content_hash = _sha256(raw)

    if not _changed(DATASET, content_hash):
        log.info("· %-24s sin cambios", DATASET)
        return False

    pdir = _partition_dir(DATASET)
    xlsx_path = pdir / "DIVIPOLA_Municipios.xlsx"
    xlsx_path.write_bytes(raw)

    # El libro trae 2 hojas ("ESRI_MAPINFO_SHEET" primero, vacía, y
    # "Municipios" con los datos reales) -- sin sheet_name explícito, pandas
    # lee la primera hoja y da un DataFrame vacío.
    df = pd.read_excel(xlsx_path, sheet_name="Municipios", header=10, dtype=str)
    df.columns = [
        "dpto_codigo", "dpto_nombre", "mpio_codigo", "mpio_nombre",
        "tipo", "longitud", "latitud", "nota",
    ]
    df = df[df["mpio_codigo"].notna()].copy()
    df["mpio_codigo"] = df["mpio_codigo"].str.strip().str.zfill(5)
    df["dpto_codigo"] = df["dpto_codigo"].str.strip().str.zfill(2)
    for col in CAMPOS_PENDIENTES:
        df[col] = pd.NA
    df["_pendiente_fuente"] = ",".join(CAMPOS_PENDIENTES)

    parquet_path = pdir / f"{DATASET}.parquet"
    df.to_parquet(parquet_path, index=False)

    _commit_hash(DATASET, content_hash)
    _write_manifest(
        DATASET, "table",
        files={"xlsx": xlsx_path, "parquet": parquet_path},
        source_url=DIVIPOLA_URL,
        descripcion="DIVIPOLA oficial (DANE): nombres/coordenadas de municipio. "
                     "Hogares/ruralidad/etnia/estrato pendientes de fuente verificada.",
        n_municipios=len(df),
        campos_pendientes=CAMPOS_PENDIENTES,
    )
    for p in (xlsx_path, parquet_path):
        _maybe_upload_oss(p)
    log.info("✓ %-24s %d municipios -> snapshot nuevo", DATASET, len(df))
    return True


def load_caracterizacion() -> Optional[pd.DataFrame]:
    """DataFrame por municipio (DIVIPOLA) con nombres/coords + columnas
    pendientes en None. Devuelve None si aún no hay snapshot."""
    m = DATA_ROOT / DATASET / "latest.json"
    if not m.exists():
        return None
    import json
    meta = json.loads(m.read_text(encoding="utf-8"))
    ruta = meta["files"]["parquet"].replace("\\", "/")
    p = Path(ruta)
    if not p.is_absolute():
        p = DATA_ROOT.parent / p
    if not p.exists():
        return None
    return pd.read_parquet(p)


def enriquecer(df: pd.DataFrame, cod_col: str, car: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Left-join de la caracterización DANE sobre `df` por código DIVIPOLA
    (5 dígitos). No inventa valores: los municipios sin caracterización
    quedan con NaN en las columnas nuevas."""
    car = car if car is not None else load_caracterizacion()
    if car is None:
        for col in ["mpio_nombre", "dpto_nombre", *CAMPOS_PENDIENTES]:
            df[col] = pd.NA
        return df
    codigos = df[cod_col].astype(str).str.strip().str.zfill(5)
    car2 = car.rename(columns={"mpio_codigo": "_cod_join"})
    out = df.assign(_cod_join=codigos).merge(car2, on="_cod_join", how="left").drop(columns="_cod_join")
    return out


def main(argv: Optional[list[str]] = None) -> int:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        fetch_divipola()
        return 0
    except Exception as e:  # noqa: BLE001
        log.error("✗ %s: %s", DATASET, e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
