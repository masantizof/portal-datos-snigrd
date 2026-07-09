"""
bart_alertas.py
================
Crawler recursivo + materializador de /ospa/Alertas/ (IDEAM/BART).

Principio crítico (confirmado en vivo, 2026-07-09): el "Last modified" que
Apache muestra para una CARPETA es el de su último cambio ESTRUCTURAL, no el
de su contenido. Ejemplo real: modelos/ figura con fecha de 2025, pero
modelos/deslizamientos/ultimo/ tiene archivos de hoy. Por eso este módulo
NUNCA decide si algo está vigente por la fecha de una carpeta padre: siempre
baja hasta el nivel de archivo y mira el Last-Modified de cada archivo.

Árbol real mapeado a mano (ver data_lake/_diagnostico/arbol_alertas.json
para el detalle completo generado por crawl_tree):

  DescensosTemperatura/{YYYYMMDD}/{excel,mapas,shape,txt}/...
  Granizo/{YYYYMMDD}/{excel,mapas,shape,txt}/...
  IndiceCalor/{YYYYMMDD}/{excel,mapas,shape,txt}/...
  TemperaturasMaximasMunicipios/{YYYYMMDD}/{csv,mapas,raster}/...  <- cruza DIVIPOLA
  TemperaturasMinimasMunicipios/{YYYYMMDD}/{csv,mapas,raster}/...  <- cruza DIVIPOLA
  datos_diarios_preliminares/*.xlsx                    (plano, ~60 archivos)
  hidroestimador_satelital/NOAA_HE_COL_{YYYYMMDD}.tif   (plano, ~200 históricos)
  modelos/deslizamientos/{Backup/, ultimo/*.csv}        <- ultimo/ es lo vigente
  modelos/incendios/{Backup/, ultimo/*.csv}             <- ultimo/ es lo vigente
  modelos/hidrologia/Alertas_vigentes.{shp,shx,dbf,prj} (shapefile directo, sin fecha)

Las carpetas organizadas por fecha guardan MUCHO histórico (decenas de
carpetas YYYYMMDD): este módulo, al materializar, sólo baja la fecha más
reciente que tenga archivos (algunas fechas quedan vacías, p.ej. sin evento
ese día) — es "consulta de datos diarios", no una réplica del archivo
histórico completo. El árbol completo sí se recorre para el mapa de
auditoría (crawl_tree/--tree), pero eso es un proceso aparte, más costoso,
que no hace falta correr en cada ciclo del cron.

Uso como script:
    python bart_alertas.py --diarias      # categorías por fecha + planas + modelos
    python bart_alertas.py --tree         # sólo el mapa de auditoría del árbol completo
    python bart_alertas.py --all          # ambas cosas

Uso desde la app / cruce_divipola.py:
    import bart_alertas as ba
    df = ba.load_temperatura_municipal("max")   # columnas: COD_DANE, TEMPERATURA
    df = ba.load_amenaza_modelo("deslizamientos")  # columnas: COD_DANE, TEXTO_AMENAZA
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import pandas as pd
import requests

from ideam_extractor import (  # noqa: F401
    SESSION, DATA_ROOT, TIMEOUT, log,
    _partition_dir, _changed, _commit_hash,
    _write_manifest, _maybe_upload_oss,
    _resolve_manifest_path, latest_meta,
)

ALERTAS_BASE = "https://bart.ideam.gov.co/ospa/Alertas/"
DIAG_DIR = DATA_ROOT / "_diagnostico"

# Algunos rásters nacionales de alta resolución (p.ej. downscaling a 30m de
# TemperaturasMaximas/MinimasMunicipios) pesan >2GB cada uno -- inviable para
# un repo de git (límite duro de GitHub: 100MB/archivo) y para un cron diario.
# Se omiten de forma auditable (queda registrado en el manifiesto, con su
# URL de origen) en vez de descargarlos o de fabricar un sustituto más chico.
MAX_DESCARGA_MB = 60

# Autoindex de Apache en este host usa formato "DD-Mon-YYYY HH:MM" (distinto
# del "YYYY-MM-DD HH:MM" que usa el índice de wrfideam/new_modelo — son
# configuraciones de mod_autoindex distintas en el mismo servidor).
#
# La fecha debe quedar atada a la MISMA fila (</a></td><td align="right">DATE):
# la fila "Parent Directory" no trae fecha propia (su celda es "&nbsp;"), así
# que un patrón .*? sin esta restricción "roba" la fecha de la fila
# siguiente y esa fila se pierde entera (confirmado: se perdía el primer
# archivo -alfabéticamente- de cada carpeta, p.ej. Alertas_vigentes.dbf).
_LISTING_RX = re.compile(
    r'href="(?P<name>[^"?][^"]*)"[^<]*</a>\s*</td>\s*<td[^>]*>\s*'
    r'(?P<date>\d{2}-[A-Za-z]{3}-\d{4})\s+(?P<time>\d{2}:\d{2})',
)


# --------------------------------------------------------------------------- #
# Listado de directorios (autoindex)
# --------------------------------------------------------------------------- #
def _listar(url: str) -> list[dict]:
    """Lista una carpeta autoindex: nombre, si es subcarpeta, y su propio
    Last-Modified (nunca el de la carpeta contenedora)."""
    r = SESSION.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for m in _LISTING_RX.finditer(r.text):
        name = m.group("name")
        if name.startswith(("?", "/")) or name in ("../",):
            continue
        when = dt.datetime.strptime(f'{m.group("date")} {m.group("time")}', "%d-%b-%Y %H:%M")
        out.append({"name": name, "is_dir": name.endswith("/"), "last_modified": when})
    return out


def _descargar(url: str, max_mb: float = MAX_DESCARGA_MB) -> Optional[bytes]:
    """GET en streaming con tope de tamaño: devuelve None (y loggea) si el
    archivo supera max_mb en vez de descargarlo completo -- protege contra
    rásters nacionales de varios GB que romperían un repo de git."""
    limite = int(max_mb * 1_000_000)
    r = SESSION.get(url, timeout=TIMEOUT * 3, stream=True)
    r.raise_for_status()
    largo = r.headers.get("Content-Length")
    if largo is not None and int(largo) > limite:
        r.close()
        log.warning("· omitido (%.1f MB > %.0f MB límite): %s", int(largo) / 1e6, max_mb, url)
        return None
    buf = bytearray()
    for chunk in r.iter_content(chunk_size=1 << 20):
        buf.extend(chunk)
        if len(buf) > limite:
            r.close()
            log.warning("· omitido (excede %.0f MB en streaming): %s", max_mb, url)
            return None
    return bytes(buf)


# --------------------------------------------------------------------------- #
# Auditoría: mapa del árbol completo (recursivo en profundidad)
# --------------------------------------------------------------------------- #
def crawl_tree(base: str = ALERTAS_BASE, max_depth: int = 6) -> list[dict]:
    """Recorre TODO el árbol en profundidad para fines de auditoría. Nunca
    decide entrar o no a una carpeta por su fecha -- eso es justo lo que este
    módulo evita hacer al materializar datos."""
    nodos: list[dict] = []
    visitados: set[str] = set()

    def _rec(url: str, depth: int) -> None:
        if depth > max_depth or url in visitados:
            return
        visitados.add(url)
        try:
            hijos = _listar(url)
        except requests.RequestException as e:
            nodos.append({"url": url, "depth": depth, "error": str(e)})
            return
        for h in hijos:
            child_url = urljoin(url, h["name"])
            nodos.append({
                "url": child_url, "depth": depth, "is_dir": h["is_dir"],
                "last_modified": h["last_modified"].isoformat(),
            })
            if h["is_dir"] and "Backup" not in h["name"]:
                _rec(child_url, depth + 1)

    _rec(base, 0)
    return nodos


def guardar_arbol(nodos: list[dict]) -> Path:
    DIAG_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "generado": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "base": ALERTAS_BASE,
        "n_nodos": len(nodos),
        "nodos": nodos,
    }
    path = DIAG_DIR / "arbol_alertas.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_tree() -> Path:
    log.info("Recorriendo árbol completo de %s (puede tardar varios minutos)...", ALERTAS_BASE)
    nodos = crawl_tree()
    path = guardar_arbol(nodos)
    log.info("✓ arbol_alertas.json: %d nodos -> %s", len(nodos), path)
    return path


# --------------------------------------------------------------------------- #
# Categorías organizadas por fecha (YYYYMMDD)
# --------------------------------------------------------------------------- #
CATEGORIAS_POR_FECHA = {
    "descensos_temperatura": ("DescensosTemperatura", ("excel", "mapas", "shape", "txt")),
    "granizo": ("Granizo", ("excel", "mapas", "shape", "txt")),
    "indice_calor": ("IndiceCalor", ("excel", "mapas", "shape", "txt")),
    "temp_max_municipios": ("TemperaturasMaximasMunicipios", ("csv", "mapas", "raster")),
    "temp_min_municipios": ("TemperaturasMinimasMunicipios", ("csv", "mapas", "raster")),
}


def _fecha_mas_reciente_con_datos(categoria_url: str, subcarpetas: tuple[str, ...]) -> Optional[str]:
    """Entre las subcarpetas YYYYMMDD de una categoría, halla la más reciente
    que sí tenga archivos en alguna de sus subcarpetas esperadas (algunas
    fechas quedan vacías, p.ej. sin evento ese día)."""
    try:
        hijos = _listar(categoria_url)
    except requests.RequestException as e:
        log.error("no se pudo listar %s: %s", categoria_url, e)
        return None
    fechas = sorted(
        (h["name"].rstrip("/") for h in hijos if h["is_dir"] and h["name"].rstrip("/").isdigit()),
        reverse=True,
    )
    for fecha in fechas:
        fecha_url = urljoin(categoria_url, fecha + "/")
        for sub in subcarpetas:
            sub_url = urljoin(fecha_url, sub + "/")
            try:
                archivos = [h for h in _listar(sub_url) if not h["is_dir"]]
            except requests.RequestException:
                continue
            if archivos:
                return fecha
    return None


def materializar_categoria_por_fecha(dataset: str, categoria_nombre: str,
                                      subcarpetas: tuple[str, ...]) -> bool:
    """Descarga todos los archivos de la fecha más reciente con datos de una
    categoría organizada por YYYYMMDD (excel/mapas/shape/txt o csv/mapas/raster)."""
    categoria_url = urljoin(ALERTAS_BASE, categoria_nombre + "/")
    fecha = _fecha_mas_reciente_con_datos(categoria_url, subcarpetas)
    if fecha is None:
        log.warning("· %-24s sin fechas con datos", dataset)
        return False

    fecha_url = urljoin(categoria_url, fecha + "/")
    pdir = _partition_dir(dataset)
    guardados: dict[str, Path] = {}
    firmas: list[str] = []
    omitidos: list[dict] = []
    for sub in subcarpetas:
        sub_url = urljoin(fecha_url, sub + "/")
        try:
            archivos = [h for h in _listar(sub_url) if not h["is_dir"]]
        except requests.RequestException:
            continue
        for h in archivos:
            file_url = urljoin(sub_url, h["name"])
            try:
                contenido = _descargar(file_url)
            except requests.RequestException as e:
                log.error("✗ %s: %s (%s)", dataset, h["name"], e)
                continue
            if contenido is None:
                omitidos.append({"archivo": f"{sub}/{h['name']}", "url": file_url})
                continue
            out_path = pdir / sub / h["name"]
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(contenido)
            guardados[f"{sub}/{h['name']}"] = out_path
            firmas.append(f"{sub}/{h['name']}|{h['last_modified'].isoformat()}")

    if not guardados:
        log.warning("· %-24s fecha %s sin archivos descargables", dataset, fecha)
        return False

    firma = "|".join(sorted(firmas))
    if not _changed(dataset, firma):
        log.info("· %-24s sin cambios (fecha %s)", dataset, fecha)
        return False

    _commit_hash(dataset, firma)
    nota = (f"Última fecha con datos publicados en {categoria_nombre}/ (BART/IDEAM). "
            "El histórico completo no se replica, sólo se consulta la fecha vigente.")
    if omitidos:
        nota += f" {len(omitidos)} archivo(s) omitido(s) por superar {MAX_DESCARGA_MB:.0f}MB (ver 'omitidos')."
    _write_manifest(
        dataset, "alerta_diaria",
        files={k: str(v) for k, v in guardados.items()},
        source_url=fecha_url, categoria=categoria_nombre, fecha=fecha,
        n_archivos=len(guardados), omitidos=omitidos,
        note=nota,
    )
    for p in guardados.values():
        _maybe_upload_oss(p)
    log.info("✓ %-24s fecha %s (%d archivos)", dataset, fecha, len(guardados))
    return True


def run_categorias_por_fecha() -> tuple[int, int]:
    ok = fail = 0
    for dataset, (nombre, subcarpetas) in CATEGORIAS_POR_FECHA.items():
        try:
            materializar_categoria_por_fecha(dataset, nombre, subcarpetas); ok += 1
        except Exception as e:  # noqa: BLE001
            log.error("✗ %s: %s", dataset, e); fail += 1
    return ok, fail


# --------------------------------------------------------------------------- #
# Categorías planas (sin subcarpetas de fecha)
# --------------------------------------------------------------------------- #
def materializar_flat(dataset: str, categoria_nombre: str,
                       solo_mas_recientes: Optional[int] = None) -> bool:
    """Descarga los archivos de una carpeta plana. Si solo_mas_recientes está
    definido, sólo baja los N archivos con Last-Modified más reciente (usado
    para hidroestimador_satelital, que guarda ~200 rásters históricos)."""
    url = urljoin(ALERTAS_BASE, categoria_nombre + "/")
    try:
        archivos = [h for h in _listar(url) if not h["is_dir"]]
    except requests.RequestException as e:
        log.error("✗ %s: %s", dataset, e)
        return False
    if not archivos:
        log.warning("· %-24s carpeta vacía", dataset)
        return False

    if solo_mas_recientes:
        archivos = sorted(archivos, key=lambda h: h["last_modified"], reverse=True)[:solo_mas_recientes]

    pdir = _partition_dir(dataset)
    guardados: dict[str, Path] = {}
    firmas: list[str] = []
    omitidos: list[dict] = []
    for h in archivos:
        file_url = urljoin(url, h["name"])
        try:
            contenido = _descargar(file_url)
        except requests.RequestException as e:
            log.error("✗ %s: %s (%s)", dataset, h["name"], e)
            continue
        if contenido is None:
            omitidos.append({"archivo": h["name"], "url": file_url})
            continue
        out_path = pdir / h["name"]
        out_path.write_bytes(contenido)
        guardados[h["name"]] = out_path
        firmas.append(f"{h['name']}|{h['last_modified'].isoformat()}")

    if not guardados:
        return False
    firma = "|".join(sorted(firmas))
    if not _changed(dataset, firma):
        log.info("· %-24s sin cambios (%d archivos)", dataset, len(guardados))
        return False

    _commit_hash(dataset, firma)
    nota = "Carpeta plana (sin subcarpetas de fecha) del árbol de Alertas BART/IDEAM."
    if omitidos:
        nota += f" {len(omitidos)} archivo(s) omitido(s) por superar {MAX_DESCARGA_MB:.0f}MB (ver 'omitidos')."
    _write_manifest(
        dataset, "alerta_diaria",
        files={k: str(v) for k, v in guardados.items()},
        source_url=url, categoria=categoria_nombre, n_archivos=len(guardados), omitidos=omitidos,
        note=nota,
    )
    for p in guardados.values():
        _maybe_upload_oss(p)
    log.info("✓ %-24s %d archivos", dataset, len(guardados))
    return True


def run_planas() -> tuple[int, int]:
    ok = fail = 0
    try:
        materializar_flat("datos_diarios_preliminares", "datos_diarios_preliminares"); ok += 1
    except Exception as e:  # noqa: BLE001
        log.error("✗ datos_diarios_preliminares: %s", e); fail += 1
    try:
        materializar_flat("hidroestimador_satelital", "hidroestimador_satelital", solo_mas_recientes=3); ok += 1
    except Exception as e:  # noqa: BLE001
        log.error("✗ hidroestimador_satelital: %s", e); fail += 1
    return ok, fail


# --------------------------------------------------------------------------- #
# modelos/{deslizamientos,incendios}/ultimo/  (siempre vigente, sin fecha)
# --------------------------------------------------------------------------- #
MODELOS_AMENAZA = {
    "deslizamientos": "modelos/deslizamientos/ultimo/",
    "incendios": "modelos/incendios/ultimo/",
}


def materializar_modelo_amenaza(categoria: str) -> bool:
    if categoria not in MODELOS_AMENAZA:
        raise ValueError(f"categoría de modelo desconocida: {categoria}")
    dataset = f"amenaza_{categoria}"
    url = urljoin(ALERTAS_BASE, MODELOS_AMENAZA[categoria])
    try:
        archivos = [h for h in _listar(url) if not h["is_dir"] and h["name"].lower().endswith(".csv")]
    except requests.RequestException as e:
        log.error("✗ %s: %s", dataset, e)
        return False
    if not archivos:
        log.warning("· %-24s sin CSV en ultimo/", dataset)
        return False

    pdir = _partition_dir(dataset)
    guardados: dict[str, Path] = {}
    firmas: list[str] = []
    for h in archivos:
        file_url = urljoin(url, h["name"])
        contenido = _descargar(file_url)
        if contenido is None:
            continue
        out_path = pdir / h["name"]
        out_path.write_bytes(contenido)
        guardados[h["name"]] = out_path
        firmas.append(f"{h['name']}|{h['last_modified'].isoformat()}")

    if not guardados:
        log.warning("· %-24s ningún CSV descargable", dataset)
        return False

    firma = "|".join(sorted(firmas))
    if not _changed(dataset, firma):
        log.info("· %-24s sin cambios", dataset)
        return False

    _commit_hash(dataset, firma)
    _write_manifest(
        dataset, "amenaza_modelo",
        files={k: str(v) for k, v in guardados.items()},
        source_url=url, categoria=categoria, n_archivos=len(guardados),
        note="Última corrida del modelo de amenaza (carpeta ultimo/): vigente pese a "
             "que modelos/ como carpeta padre puede mostrar una fecha antigua.",
    )
    for p in guardados.values():
        _maybe_upload_oss(p)
    log.info("✓ %-24s %d archivos", dataset, len(guardados))
    return True


# --------------------------------------------------------------------------- #
# modelos/hidrologia/  (shapefile directo, sin subcarpeta de fecha)
# --------------------------------------------------------------------------- #
def _shapefile_a_geojson(shp_path: Path) -> dict:
    """Convierte un shapefile (.shp+.shx+.dbf ya descargados junto a
    shp_path, mismo nombre base) a GeoJSON usando pyshp (sin geopandas)."""
    import shapefile  # pyshp

    # encoding="latin-1" nunca falla al decodificar (mapea todos los bytes):
    # los atributos de IDEAM (nombres de municipio con tildes/ñ) vienen en
    # latin-1, no utf-8, igual que los CSV de modelos/*.
    sf = shapefile.Reader(str(shp_path.with_suffix("")), encoding="latin-1")
    campos = [f[0] for f in sf.fields[1:]]
    features = []
    for sr in sf.shapeRecords():
        features.append({
            "type": "Feature",
            "geometry": sr.shape.__geo_interface__,
            "properties": dict(zip(campos, sr.record)),
        })
    return {"type": "FeatureCollection", "features": features}


def materializar_modelo_hidrologia() -> bool:
    dataset = "amenaza_hidrologia"
    url = urljoin(ALERTAS_BASE, "modelos/hidrologia/")
    try:
        archivos = [h for h in _listar(url) if not h["is_dir"]]
    except requests.RequestException as e:
        log.error("✗ %s: %s", dataset, e)
        return False
    partes = {h["name"]: h for h in archivos if h["name"].lower().startswith("alertas_vigentes.")}
    if not partes:
        log.warning("· %-24s sin shapefile Alertas_vigentes", dataset)
        return False

    pdir = _partition_dir(dataset)
    guardados: dict[str, Path] = {}
    firmas: list[str] = []
    for name, h in partes.items():
        file_url = urljoin(url, name)
        contenido = _descargar(file_url)
        if contenido is None:
            continue
        out_path = pdir / name
        out_path.write_bytes(contenido)
        guardados[name] = out_path
        firmas.append(f"{name}|{h['last_modified'].isoformat()}")

    if "Alertas_vigentes.shp" not in guardados and not any(n.lower().endswith(".shp") for n in guardados):
        log.warning("· %-24s shapefile omitido (excede %.0fMB)", dataset, MAX_DESCARGA_MB)
        return False

    firma = "|".join(sorted(firmas))
    if not _changed(dataset, firma):
        log.info("· %-24s sin cambios", dataset)
        return False

    geojson_path = None
    shp_path = next((p for n, p in guardados.items() if n.lower().endswith(".shp")), None)
    if shp_path is not None:
        try:
            geo = _shapefile_a_geojson(shp_path)
            geojson_path = pdir / "Alertas_vigentes.geojson"
            geojson_path.write_text(json.dumps(geo, ensure_ascii=False), encoding="utf-8")
            guardados["geojson"] = geojson_path
        except Exception as e:  # noqa: BLE001
            log.error("no se pudo convertir shapefile a GeoJSON (%s): %s", dataset, e)

    _commit_hash(dataset, firma)
    _write_manifest(
        dataset, "vector",
        files={k: str(v) for k, v in guardados.items()},
        source_url=url, n_archivos=len(guardados),
        note="Alertas hidrológicas vigentes (shapefile IDEAM, convertido a GeoJSON con pyshp).",
    )
    for p in guardados.values():
        _maybe_upload_oss(p)
    log.info("✓ %-24s %d archivos%s", dataset, len(guardados), " + geojson" if geojson_path else "")
    return True


def run_modelos() -> tuple[int, int]:
    ok = fail = 0
    for categoria in MODELOS_AMENAZA:
        try:
            materializar_modelo_amenaza(categoria); ok += 1
        except Exception as e:  # noqa: BLE001
            log.error("✗ amenaza_%s: %s", categoria, e); fail += 1
    try:
        materializar_modelo_hidrologia(); ok += 1
    except Exception as e:  # noqa: BLE001
        log.error("✗ amenaza_hidrologia: %s", e); fail += 1
    return ok, fail


# --------------------------------------------------------------------------- #
# Loaders — contrato que consume cruce_divipola.py
# --------------------------------------------------------------------------- #
def load_temperatura_municipal(tipo: str) -> Optional[pd.DataFrame]:
    """Última temperatura municipal (max o min). Columnas devueltas:
    COD_DANE, TEMPERATURA (contrato usado por cruce_divipola.py)."""
    if tipo not in ("max", "min"):
        raise ValueError("tipo debe ser 'max' o 'min'")
    dataset = f"temp_{tipo}_municipios"
    try:
        meta = latest_meta(dataset)
    except FileNotFoundError:
        return None
    files = meta.get("files", {})
    nombre = next((n for n in files if n.startswith("csv/") and "Municipal" in n), None)
    if nombre is None:
        return None
    path = _resolve_manifest_path(files[nombre])
    if not path.exists():
        return None
    df = pd.read_csv(path, dtype=str)
    col_temp = next((c for c in df.columns if c.startswith("TMAX_") or c.startswith("TMIN_")), None)
    if "COD_MUN" not in df.columns or col_temp is None:
        return None
    out = df[["COD_MUN", col_temp]].rename(columns={"COD_MUN": "COD_DANE", col_temp: "TEMPERATURA"})
    out["TEMPERATURA"] = pd.to_numeric(out["TEMPERATURA"], errors="coerce")
    return out


def load_amenaza_modelo(categoria: str) -> Optional[pd.DataFrame]:
    """Última corrida del modelo de amenaza (deslizamientos o incendios).
    Columnas mínimas garantizadas: COD_DANE, TEXTO_AMENAZA (contrato usado
    por cruce_divipola.py). También incluye REGION/DEPARTAMENTO/MUNICIPIO
    cuando el CSV las trae (para agregaciones por región en la UI) -- estas
    extra no rompen el contrato: cruce_divipola sólo toma las columnas que
    tiene registradas."""
    if categoria not in MODELOS_AMENAZA:
        raise ValueError(f"categoría de modelo desconocida: {categoria}")
    dataset = f"amenaza_{categoria}"
    try:
        meta = latest_meta(dataset)
    except FileNotFoundError:
        return None
    files = meta.get("files", {})
    nombre = next((n for n in files if n.startswith("amenaza_")), None)
    if nombre is None:
        return None
    path = _resolve_manifest_path(files[nombre])
    if not path.exists():
        return None
    df = pd.read_csv(path, sep=";", dtype=str, encoding="latin-1")
    if "COD_DANE" not in df.columns or "TEXTO_AMENAZA" not in df.columns:
        return None
    cols = [c for c in ("COD_DANE", "TEXTO_AMENAZA", "REGION", "DEPARTAMENTO", "MUNICIPIO") if c in df.columns]
    return df[cols].copy()


def load_alerta(categoria_nombre: str) -> Optional[dict]:
    """Manifiesto de cualquier categoría materializada, por su nombre lógico
    de dataset (p.ej. 'descensos_temperatura', 'granizo', 'amenaza_hidrologia')."""
    try:
        return latest_meta(categoria_nombre)
    except FileNotFoundError:
        return None


# --------------------------------------------------------------------------- #
# Orquestación
# --------------------------------------------------------------------------- #
def run_diarias() -> tuple[int, int]:
    ok = fail = 0
    for runner in (run_categorias_por_fecha, run_planas, run_modelos):
        o, f = runner(); ok += o; fail += f
    return ok, fail


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Crawler y materializador de /ospa/Alertas/ (BART/IDEAM)")
    ap.add_argument("--diarias", action="store_true", help="categorías por fecha + planas + modelos")
    ap.add_argument("--tree", action="store_true", help="mapa de auditoría del árbol completo (lento)")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args(argv)
    if not any([args.diarias, args.tree, args.all]):
        args.diarias = True

    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    ok = fail = 0
    if args.all or args.diarias:
        o, f = run_diarias(); ok += o; fail += f
    if args.all or args.tree:
        run_tree()
    log.info("Alertas BART: %d ok, %d con error", ok, fail)
    return 1 if ok == 0 and fail > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
