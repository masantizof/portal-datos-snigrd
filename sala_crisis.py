"""
sala_crisis.py
================
Registro histórico de emergencias (Sala de Crisis UNGRD). Es un insumo
ESTÁTICO (no forma parte del cron de ingesta): se carga una vez a
data/reference/emergencias_sala_crisis.parquet y se actualizará por
separado en el futuro. No consulta ninguna fuente en vivo.

Uso desde la app:
    from sala_crisis import load_emergencias, recurrencia_por_municipio_evento
    df = load_emergencias()                       # una fila por emergencia
    rec = recurrencia_por_municipio_evento(df)     # conteos por (municipio, evento)
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent
PARQUET_PATH = ROOT / "data" / "reference" / "emergencias_sala_crisis.parquet"

COL_COD_MUNICIPIO = "Codigo Municipio"
COL_DEPARTAMENTO = "Nombre Departamento"
COL_MUNICIPIO = "Nombre Municipio"
COL_EVENTO = "EVENTO"
COL_FECHA = "FECHA_DATETIME"

CAMPOS_AFECTACION = [
    "FAMILIAS", "PERSONAS", "MUERTOS", "HERIDOS", "DESAPA.",
    "VIVIENDAS DESTRUIDAS", "VIVIENDAS AVERIADAS",
]

# --------------------------------------------------------------------------- #
# Enmascarado de datos personales en COMENTARIOS (texto libre institucional).
# Best-effort por regex: cubre teléfonos y secuencias numéricas largas que
# suelen ser cédulas/contacto. No es un NER; no garantiza remoción total de
# nombres propios (ver limitación documentada en Metodología y fuentes).
# --------------------------------------------------------------------------- #
_PAT_TELEFONO = re.compile(r"\b(3\d{9}|\d{7,10})\b")
_PAT_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _enmascarar_pii(texto: object) -> Optional[str]:
    if texto is None or (isinstance(texto, float) and pd.isna(texto)):
        return None
    s = str(texto)
    s = _PAT_EMAIL.sub("[correo oculto]", s)
    s = _PAT_TELEFONO.sub("[número oculto]", s)
    return s


def _normalizar_codigo(serie: pd.Series) -> pd.Series:
    return serie.astype(str).str.strip().str.zfill(5)


def load_emergencias() -> pd.DataFrame:
    """Una fila por emergencia registrada. COMENTARIOS viene enmascarado
    (teléfonos/correos ocultos) porque la app es pública."""
    df = pd.read_parquet(PARQUET_PATH)
    df[COL_COD_MUNICIPIO] = _normalizar_codigo(df[COL_COD_MUNICIPIO])
    if "COMENTARIOS" in df.columns:
        df["COMENTARIOS"] = df["COMENTARIOS"].apply(_enmascarar_pii)
    return df


def agregados_por_municipio(df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Nº de emergencias y sumas de afectación por municipio (todas las épocas/eventos)."""
    df = df if df is not None else load_emergencias()
    agg = df.groupby([COL_COD_MUNICIPIO, COL_MUNICIPIO, COL_DEPARTAMENTO]).agg(
        n_emergencias=(COL_EVENTO, "count"),
        familias=("FAMILIAS", "sum"),
        personas=("PERSONAS", "sum"),
        muertos=("MUERTOS", "sum"),
    ).reset_index()
    return agg


def recurrencia_por_municipio_evento(df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Nº de emergencias por (municipio, tipo de evento) — para cruzar con el
    índice/amenaza dominante de cada municipio y con las alertas vigentes."""
    df = df if df is not None else load_emergencias()
    agg = df.groupby([COL_COD_MUNICIPIO, COL_MUNICIPIO, COL_EVENTO]).agg(
        n_emergencias=(COL_EVENTO, "count"),
        familias=("FAMILIAS", "sum"),
        personas=("PERSONAS", "sum"),
    ).reset_index()
    return agg


def agregados_por_evento(df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    df = df if df is not None else load_emergencias()
    agg = df.groupby(COL_EVENTO).agg(
        n_emergencias=(COL_EVENTO, "count"),
        familias=("FAMILIAS", "sum"),
        personas=("PERSONAS", "sum"),
        muertos=("MUERTOS", "sum"),
    ).reset_index().sort_values("n_emergencias", ascending=False)
    return agg


def agregados_por_anio(df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    df = df if df is not None else load_emergencias()
    d = df.copy()
    d["anio"] = pd.to_datetime(d[COL_FECHA]).dt.year
    agg = d.groupby("anio").agg(
        n_emergencias=(COL_EVENTO, "count"),
        familias=("FAMILIAS", "sum"),
        personas=("PERSONAS", "sum"),
    ).reset_index().sort_values("anio")
    return agg


def eventos_por_departamento(df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Conteos por (departamento, evento) — para cruzar con alertas hidrológicas,
    que están zonificadas por departamento y no por municipio."""
    df = df if df is not None else load_emergencias()
    agg = df.groupby([COL_DEPARTAMENTO, COL_EVENTO]).agg(
        n_emergencias=(COL_EVENTO, "count"),
    ).reset_index()
    return agg
