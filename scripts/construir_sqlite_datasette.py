"""
scripts/construir_sqlite_datasette.py
=========================================
Consolida las tablas municipales (índices de riesgo SNGRD, DANE, Sala de
Crisis, temperatura y amenaza de modelos BART) en una base SQLite para
servir con Datasette (API consultable, nivel avanzado — ver Fuentes,
descargas y API). No inventa cruces: usa exactamente el mismo motor de
cruce_divipola.py que la app, así que "sin dato" se representa igual en
ambos lugares.

Debe correrse DESPUÉS de sembrar data_lake/ (extractores + bart_alertas.py).
El .sqlite resultante se sube a mano (o por script) al Space de Hugging Face
que sirve Datasette — no se genera dentro del contenedor de HF porque ese
build no tiene acceso a las fuentes de IDEAM.

Uso:
    python scripts/construir_sqlite_datasette.py --out datasette_space/db.sqlite
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cruce_divipola as cd  # noqa: E402


def _tabla_desde_df(conn: sqlite3.Connection, nombre: str, df) -> None:
    if df is None or df.empty:
        return
    df.to_sql(nombre, conn, if_exists="replace", index=False)


def construir(out_path: Path) -> dict:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    conn = sqlite3.connect(str(out_path))

    resumen = {}

    base, _ = cd.cargar_base_municipal()
    _tabla_desde_df(conn, "municipios", base)
    resumen["municipios"] = len(base)

    # Una tabla por fuente registrada (cruda, sin prefijo de columnas).
    for fid, meta in cd.FUENTES.items():
        df = meta["loader"]()
        if df is None or df.empty:
            resumen[fid] = 0
            continue
        _tabla_desde_df(conn, fid, df)
        resumen[fid] = len(df)

    # Vista amplia: universo base + todas las fuentes cruzadas por DIVIPOLA
    # (misma lógica que usa la página "Consulta y cruce municipal").
    cruzado = cd.cruzar(list(cd.FUENTES.keys()), base=base)
    _tabla_desde_df(conn, "cruce_municipal", cruzado)
    resumen["cruce_municipal"] = len(cruzado)

    conn.commit()
    conn.close()
    return resumen


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Construye la base SQLite para Datasette")
    ap.add_argument("--out", default="datasette_space/db.sqlite", help="ruta de salida del .sqlite")
    args = ap.parse_args(argv)

    out_path = ROOT / args.out if not Path(args.out).is_absolute() else Path(args.out)
    resumen = construir(out_path)

    print(f"Base SQLite escrita en {out_path} ({out_path.stat().st_size / 1e6:.1f} MB):")
    for tabla, n in resumen.items():
        print(f"  - {tabla}: {n} filas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
