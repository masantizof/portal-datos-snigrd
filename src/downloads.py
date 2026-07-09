"""
src/downloads.py
=================
Helpers de descarga (CSV / GeoJSON / PNG) para que cada sección permita
bajar tanto los datos como las imágenes de su análisis.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st


def boton_csv(df: pd.DataFrame, nombre_archivo: str, etiqueta: str = "⬇️ Descargar CSV", key: Optional[str] = None) -> None:
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        etiqueta, data=csv, file_name=nombre_archivo, mime="text/csv",
        key=key or f"csv_{nombre_archivo}",
    )


def boton_geojson(geojson: dict, nombre_archivo: str, etiqueta: str = "⬇️ Descargar GeoJSON", key: Optional[str] = None) -> None:
    data = json.dumps(geojson, ensure_ascii=False).encode("utf-8")
    st.download_button(
        etiqueta, data=data, file_name=nombre_archivo, mime="application/geo+json",
        key=key or f"geojson_{nombre_archivo}",
    )


def boton_png(ruta_png: str | Path, nombre_archivo: str, etiqueta: str = "⬇️ Descargar imagen (PNG)", key: Optional[str] = None) -> None:
    ruta_png = Path(ruta_png)
    if not ruta_png.exists():
        st.caption("Imagen no disponible para descarga.")
        return
    st.download_button(
        etiqueta, data=ruta_png.read_bytes(), file_name=nombre_archivo, mime="image/png",
        key=key or f"png_{nombre_archivo}",
    )


def boton_generico(datos: bytes, nombre_archivo: str, mime: str, etiqueta: str, key: Optional[str] = None) -> None:
    st.download_button(etiqueta, data=datos, file_name=nombre_archivo, mime=mime, key=key or f"gen_{nombre_archivo}")
