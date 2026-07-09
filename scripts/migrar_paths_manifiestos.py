"""
scripts/migrar_paths_manifiestos.py
=======================================
Migra los `files{}` de cada data_lake/*/latest.json a rutas relativas a la
raíz del repo (ej. "data_lake/dataset/dt=.../archivo.ext").

Por qué hizo falta: los manifiestos generados corriendo los extractores
LOCALMENTE en Windows sin fijar IDEAM_DATA_ROOT=data_lake quedaron con
rutas ABSOLUTAS de esa máquina (p.ej. "F:/UNGRD/Portal Datos SNIGRD/...")
horneadas en el JSON -- que no existen en Streamlit Cloud (Linux,
/mount/src/...). Los datos ya descargados no se pierden, solo se reescribe
el puntero. `_write_manifest()` ya no puede volver a generar este problema
(ver ideam_extractor._relativizar_para_manifest), así que este script es
un arreglo de una sola vez para lo que ya estaba commiteado.

Uso:
    python scripts/migrar_paths_manifiestos.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "data_lake"

MARCADOR = "data_lake/"


def _relativizar(valor: str) -> str:
    texto = str(valor).replace("\\", "/")
    idx = texto.rfind(MARCADOR)
    if idx == -1:
        return texto
    return texto[idx:]


def main() -> int:
    migrados = 0
    for manifest_path in sorted(DATA_ROOT.glob("*/latest.json")):
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = data.get("files")
        if not files:
            continue
        nuevos = {k: _relativizar(v) for k, v in files.items()}
        if nuevos != files:
            data["files"] = nuevos
            manifest_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            migrados += 1
            print(f"migrado: {manifest_path.relative_to(ROOT).as_posix()}")

    print(f"\n{migrados} manifiestos migrados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
