"""
ideam_wrf_cpt.py
================
Extensión del flujo de ideam_extractor.py. Agrega dos familias:

  A) Modelo grillado descargable:
       - WRF 00Z Colombia  -> NetCDF y GeoTIFF
       - GFS 06Z Colombia  -> GRIB2
     (datos reales, se procesan sin ArcGIS con xarray/cfgrib/rasterio)

  B) CPT — Predicción mensual (estacional) de IDEAM:
       imágenes PNG por variable (precip/temp/viento), 6 meses, 6 productos.

Nota de alcance (Portal de Datos SNIGRD): esta versión NO incluye el
clasificador de fase ENSO/ONI de la app v1 (visor ENSO) — este portal es de
consulta y cruce de datos, no de análisis interpretativo.

Reutiliza toda la infraestructura del extractor base (sesión con reintentos,
dedup por hash, manifiesto latest.json, subida opcional a OSS).

Uso:
    python ideam_wrf_cpt.py --wrf --cpt
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from typing import Optional

# Reutilizamos los internos del extractor base (mismo directorio).
from ideam_extractor import (  # noqa: F401
    SESSION, DATA_ROOT, TIMEOUT, log,
    _sha256, _partition_dir, _changed, _commit_hash,
    _write_manifest, _maybe_upload_oss,
)

import requests

# Sesión sin reintentos para los HEAD de "¿existe esta URL?": si el CPT
# tiene decenas de combinaciones producto×mes a verificar, reintentar 3
# veces con backoff exponencial en cada URL que falla multiplica un timeout
# corto en una espera larga (causaba colgados de decenas de minutos).
_HEAD_SESSION = requests.Session()
_HEAD_SESSION.headers.update(SESSION.headers)


# --------------------------------------------------------------------------- #
# A) Modelo grillado: WRF / GFS
# --------------------------------------------------------------------------- #
WRF_BASE = "https://bart.ideam.gov.co/wrfideam/new_modelo"

MODEL_DIRS = {
    "wrf00_netcdf": (f"{WRF_BASE}/WRF00COLOMBIA/netcdf", (".nc", ".nc4", ".netcdf")),
    "wrf00_tif":    (f"{WRF_BASE}/WRF00COLOMBIA/tif",    (".tif", ".tiff")),
    "gfs06_grib2":  (f"{WRF_BASE}/GFS06COLOMBIA/grib2",  (".grb2", ".grib2", ".grb")),
}

# Regex para parsear el autoindex de Apache (nombre + fecha de modificación).
_AUTOINDEX_RX = re.compile(
    r'href="(?P<name>[^"?][^"]*)".*?'
    r'(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<time>\d{2}:\d{2})',
    re.S,
)


def _list_autoindex(url: str, exts: tuple[str, ...]) -> list[tuple[str, dt.datetime]]:
    """Lista (nombre, fecha) de un índice de directorio, filtrando por extensión."""
    r = SESSION.get(url if url.endswith("/") else url + "/", timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for m in _AUTOINDEX_RX.finditer(r.text):
        name = m.group("name")
        if name.endswith("/") or name.startswith(("?", "/")):
            continue
        if not name.lower().endswith(exts):
            continue
        when = dt.datetime.strptime(f'{m.group("date")} {m.group("time")}', "%Y-%m-%d %H:%M")
        out.append((name, when))
    return out


def fetch_model_latest(dataset: str, url: str, exts: tuple[str, ...]) -> bool:
    """Descarga el archivo más reciente de un directorio de modelo (WRF/GFS)."""
    base = url if url.endswith("/") else url + "/"
    files = _list_autoindex(base, exts)
    if not files:
        log.warning("· %-18s sin archivos en %s", dataset, url)
        return False
    name, when = max(files, key=lambda x: x[1])
    file_url = base + name

    sig = f"{name}|{when.isoformat()}"
    if not _changed(dataset, sig):
        log.info("· %-18s sin corrida nueva (%s)", dataset, name)
        return False

    r = SESSION.get(file_url, timeout=TIMEOUT * 3)  # binarios grandes
    r.raise_for_status()
    blob = r.content

    pdir = _partition_dir(dataset)
    out_path = pdir / name
    out_path.write_bytes(blob)

    _commit_hash(dataset, sig)
    _write_manifest(
        dataset, "grid",
        files={"data": out_path},
        source_url=file_url, filename=name,
        model_run=when.isoformat(), size_bytes=len(blob),
        note="Grilla de modelo: procesar con xarray/cfgrib/rasterio (sin ArcGIS).",
    )
    _maybe_upload_oss(out_path)
    log.info("✓ %-18s %s (%.1f MB)", dataset, name, len(blob) / 1e6)
    return True


def run_models() -> tuple[int, int]:
    ok = fail = 0
    for ds, (url, exts) in MODEL_DIRS.items():
        try:
            fetch_model_latest(ds, url, exts); ok += 1
        except Exception as e:  # noqa: BLE001
            log.error("✗ %s: %s", ds, e); fail += 1
    return ok, fail


# --------------------------------------------------------------------------- #
# B) CPT — Predicción mensual (imágenes PNG, patrón de URL conocido)
# --------------------------------------------------------------------------- #
CPT_BASE = f"{WRF_BASE}/CPT/gif/PREDICCION_MENSUAL"

CPT_VARS = {"PREC": "precipitacion", "TEMP": "temperatura", "VIEN": "viento"}
CPT_PRODUCTS = ["CLIMA", "DETER", "INDICE", "PROBVALORDET", "PROB", "PROB1090"]
CPT_MESES = range(1, 7)

CPT_HEAD_TIMEOUT = 12


def _exists(url: str) -> bool:
    try:
        return _HEAD_SESSION.head(url, timeout=CPT_HEAD_TIMEOUT, allow_redirects=True).status_code == 200
    except requests.RequestException:
        return False


def fetch_cpt(var_suffix: str = "PREC") -> bool:
    """Descarga el set de imágenes CPT de una variable (hasta 6 productos × 6 meses).

    Verifica con HEAD cuáles URLs existen antes de descargar; si ninguna
    existe, escribe un manifiesto "unavailable" para que la app distinga
    "no publicado por CPT" de "nunca se corrió el extractor"."""
    if var_suffix not in CPT_VARS:
        raise ValueError(f"variable CPT desconocida: {var_suffix}")
    dataset = f"cpt_prediccion_{CPT_VARS[var_suffix]}"

    candidatos = [
        (prod, mes, f"{prod}MES{mes}{var_suffix}.png")
        for prod in CPT_PRODUCTS for mes in CPT_MESES
    ]
    existentes = [
        (prod, mes, fname) for prod, mes, fname in candidatos
        if _exists(f"{CPT_BASE}/{fname}")
    ]

    if not existentes:
        log.warning("· %-18s ninguna imagen publicada (var %s, %d URLs verificadas)",
                     dataset, var_suffix, len(candidatos))
        _write_manifest(
            dataset, "unavailable",
            files={},
            source_url=CPT_BASE, variable=CPT_VARS[var_suffix],
            n_images=0,
            note=f"El CPT de IDEAM no tiene publicada la variable '{CPT_VARS[var_suffix]}' "
                 "en la corrida más reciente (verificado con HEAD, no es un error de la app).",
        )
        return False

    pdir = _partition_dir(dataset)
    saved, hashes = {}, []
    for prod, mes, fname in existentes:
        url = f"{CPT_BASE}/{fname}"
        try:
            r = SESSION.get(url, timeout=TIMEOUT)
            if not r.ok:
                continue
            (pdir / fname).write_bytes(r.content)
            saved[f"{prod}_mes{mes}"] = pdir / fname
            hashes.append(_sha256(r.content))
        except requests.RequestException:
            continue

    if not saved:
        log.warning("· %-18s HEAD confirmó %d URLs pero GET falló en todas", dataset, len(existentes))
        return False

    combined = _sha256("".join(sorted(hashes)).encode())
    if not _changed(dataset, combined):
        log.info("· %-18s sin cambios (%d imgs)", dataset, len(saved))
        return False

    _commit_hash(dataset, combined)
    _write_manifest(
        dataset, "image_set",
        files={k: str(v) for k, v in saved.items()},
        source_url=CPT_BASE, variable=CPT_VARS[var_suffix],
        n_images=len(saved), content_hash=combined,
        note="Predicción estacional CPT, 6 meses (imágenes de IDEAM/CPT).",
    )
    for p in saved.values():
        _maybe_upload_oss(p)
    log.info("✓ %-18s %d imágenes (de %d verificadas)", dataset, len(saved), len(existentes))
    return True


def run_cpt() -> tuple[int, int]:
    ok = fail = 0
    for suffix in CPT_VARS:
        try:
            fetch_cpt(suffix); ok += 1
        except Exception as e:  # noqa: BLE001
            log.error("✗ cpt_%s: %s", suffix, e); fail += 1
    return ok, fail


# --------------------------------------------------------------------------- #
# Orquestación
# --------------------------------------------------------------------------- #
def run_all() -> tuple[int, int]:
    ok = fail = 0
    for runner in (run_models, run_cpt):
        o, f = runner(); ok += o; fail += f
    return ok, fail


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="WRF/GFS + CPT (extensión del extractor)")
    ap.add_argument("--wrf", action="store_true", help="grillas WRF/GFS")
    ap.add_argument("--cpt", action="store_true", help="predicción mensual CPT")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args(argv)
    if not any([args.wrf, args.cpt, args.all]):
        args.all = True

    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    ok = fail = 0
    if args.all or args.wrf:
        o, f = run_models(); ok += o; fail += f
    if args.all or args.cpt:
        o, f = run_cpt(); ok += o; fail += f
    log.info("WRF/CPT: %d ok, %d con error", ok, fail)
    return 1 if ok == 0 and fail > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
