"""
simplificar_indices_riesgo.py
==============================
Preparación ÚNICA (se corre una vez, en local; NO forma parte de la app
desplegada ni del pipeline de ingesta diaria).

DatosIndice.geojson (252 MB, geometría a resolución catastral) es la capa de
índices de riesgo municipal del SNGRD que espera `ideam_enso_risk.py
--indices`. A esa resolución es inviable de: (a) commitear a GitHub, y
(b) renderizar en un mapa Leaflet/folium en el navegador.

Este script SOLO simplifica la geometría (Douglas-Peucker, topología
preservada) y redondea precisión de coordenadas. No toca ni recalcula
ninguno de los valores de los índices de riesgo (I_IF, I_Inundaci, etc.):
esos se copian tal cual. Salida pensada para choropleth nacional/departamental,
no para catastro.

Uso:
    python scripts/simplificar_indices_riesgo.py \
        --entrada DatosIndice.geojson \
        --salida data/reference/indices_riesgo_municipal.geojson \
        --tolerancia 0.001
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from shapely.geometry import shape, mapping


def main() -> int:
    ap = argparse.ArgumentParser(description="Simplifica geometría de la capa de índices de riesgo municipal")
    ap.add_argument("--entrada", required=True, type=Path)
    ap.add_argument("--salida", required=True, type=Path)
    ap.add_argument("--tolerancia", type=float, default=0.001,
                     help="grados (~111 m/grado en el ecuador); default 0.001 ~ 111 m")
    ap.add_argument("--decimales", type=int, default=5, help="precisión de coordenadas tras simplificar")
    args = ap.parse_args()

    print(f"Leyendo {args.entrada} ({args.entrada.stat().st_size/1e6:.1f} MB)...")
    geo = json.loads(args.entrada.read_text(encoding="utf-8"))
    feats = geo["features"]
    print(f"{len(feats)} municipios encontrados.")

    out_feats = []
    for i, f in enumerate(feats):
        geom = shape(f["geometry"])
        simp = geom.simplify(args.tolerancia, preserve_topology=True)
        gj = mapping(simp)

        def _round_coords(coords):
            if isinstance(coords[0], (list, tuple)):
                return [_round_coords(c) for c in coords]
            return [round(c, args.decimales) for c in coords]

        gj["coordinates"] = _round_coords(gj["coordinates"])
        out_feats.append({
            "type": "Feature",
            "properties": f["properties"],
            "geometry": gj,
        })
        if (i + 1) % 200 == 0:
            print(f"  ...{i + 1}/{len(feats)}")

    out = {
        "type": "FeatureCollection",
        "name": geo.get("name", "indices_riesgo_municipal"),
        "crs": geo.get("crs"),
        "features": out_feats,
    }

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    size_mb = args.salida.stat().st_size / 1e6
    print(f"Escrito {args.salida} ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
