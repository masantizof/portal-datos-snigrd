"""
scripts/smoke_test_apptest.py
================================
Smoke test con streamlit.testing.v1.AppTest: corre cada página de forma
aislada (sin servidor real) y falla si alguna lanza una excepción no
controlada. No reemplaza pruebas manuales en el navegador, pero atrapa
errores de import/lógica básica antes de desplegar.

Uso: python scripts/smoke_test_apptest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent

PAGINAS = [
    "pages/0_Inicio.py",
    "pages/1_Consulta_cruce_municipal.py",
    "pages/2_Alertas.py",
    "pages/3_Observacion_diaria.py",
    "pages/4_Pronostico.py",
    "pages/5_Fuentes_descargas_API.py",
    "pages/6_Metodologia_y_fuentes.py",
]


def main() -> int:
    fallos = []
    for pagina in PAGINAS:
        ruta = ROOT / pagina
        at = AppTest.from_file(str(ruta), default_timeout=60)
        at.run()
        if at.exception:
            fallos.append((pagina, at.exception))
            print(f"[FAIL] {pagina}")
            for exc in at.exception:
                print(f"    {exc.value if hasattr(exc, 'value') else exc}")
        else:
            print(f"[OK]   {pagina} ({len(at.get('warning'))} warnings, sin excepciones)")

    print()
    if fallos:
        print(f"{len(fallos)}/{len(PAGINAS)} páginas con excepción.")
        return 1
    print(f"Las {len(PAGINAS)} páginas corrieron sin excepciones.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
