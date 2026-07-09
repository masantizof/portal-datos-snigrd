"""
scripts/generar_api_datasets.py
==================================
Genera api/datasets.json: un manifiesto de "API de sólo lectura" que apunta
a los archivos crudos de cada dataset vía raw.githubusercontent.com. No
levanta ningún servidor — es sólo un índice JSON versionado en el repo que
cualquiera puede consumir con un GET normal (`requests.get(url).json()`).

Debe correrse DESPUÉS de cada ingesta (mismo cron que corre los
extractores), una vez que el push ya dejó los archivos en la rama por
defecto — las URLs raw sólo sirven contenido ya commiteado.

Uso:
    python scripts/generar_api_datasets.py --repo TU_USUARIO/portal-datos-snigrd
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "data_lake"
OUT_PATH = ROOT / "api" / "datasets.json"

RAW_BASE_TEMPLATE = "https://raw.githubusercontent.com/{repo}/main/"


def _raw_url(repo: str, ruta_local: Path) -> str:
    rel = ruta_local.relative_to(ROOT).as_posix()
    return RAW_BASE_TEMPLATE.format(repo=repo) + rel


def generar(repo: str) -> dict:
    datasets = {}
    if not DATA_ROOT.exists():
        return {"repo": repo, "generado": None, "datasets": {}}

    for ds_dir in sorted(DATA_ROOT.iterdir()):
        manifest_path = ds_dir / "latest.json"
        if ds_dir.name.startswith("_") or not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        archivos = {}
        for clave, ruta in manifest.get("files", {}).items():
            p = Path(ruta)
            if not p.is_absolute():
                p = ROOT / ruta
            if p.exists():
                archivos[clave] = _raw_url(repo, p)
        datasets[ds_dir.name] = {
            "kind": manifest.get("kind"),
            "updated_at": manifest.get("updated_at"),
            "source_url": manifest.get("source_url"),
            "manifest_url": _raw_url(repo, manifest_path),
            "files": archivos,
        }

    import datetime as dt
    return {
        "repo": repo,
        "generado": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "nota": "API de sólo lectura: cada URL sirve el archivo crudo del último snapshot "
                "vía raw.githubusercontent.com. No hay endpoint de consulta/filtrado — para "
                "eso ver la capa Datasette (nivel avanzado, ver README).",
        "datasets": datasets,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Genera api/datasets.json")
    ap.add_argument("--repo", required=True, help="usuario/repo de GitHub (para las URLs raw)")
    args = ap.parse_args(argv)

    manifest = generar(args.repo)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"api/datasets.json escrito: {len(manifest['datasets'])} datasets -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
