"""
pages/5_Fuentes_descargas_API.py
====================================
Catálogo navegable de todos los datasets del data_lake (qué son, cuándo se
actualizaron, de qué fuente vienen, descarga en su formato nativo) y la
documentación de la API de sólo lectura (api/datasets.json + Datasette).
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import loaders, ui  # noqa: E402
from src.downloads import boton_csv, boton_geojson, boton_png, boton_generico  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _ruta_existente(files: dict, clave: str) -> Path | None:
    """Path(files.get(clave, "")) si la clave existe y el archivo está en
    disco -- OJO: Path("").exists() da True (lo resuelve como '.', el
    directorio actual), así que sin el chequeo de cadena vacía primero
    intenta leer un directorio como si fuera un archivo (PermissionError)."""
    ruta = files.get(clave)
    if not ruta:
        return None
    p = Path(ruta)
    return p if p.exists() else None


ui.header(
    "Fuentes, descargas y API",
    "Catálogo completo de los datos que alimentan el portal: fuente, fecha de última "
    "actualización y descarga directa. Todo proviene de snapshots periódicos — el "
    "portal <b>nunca</b> consulta IDEAM/DANE en vivo.",
)

tab_catalogo, tab_api = st.tabs(["📚 Catálogo y descargas", "🔌 API"])

with tab_catalogo:
    disponibles = set(loaders.datasets_disponibles())
    n_total = len(loaders.CATALOGO)
    n_disp = len(disponibles & set(loaders.CATALOGO))

    ui.kpi_row([
        {"label": "Datasets en el catálogo", "value": str(n_total), "icon": "📚"},
        {"label": "Con snapshot disponible", "value": str(n_disp), "icon": "✅"},
        {"label": "Pendientes / sin snapshot", "value": str(n_total - n_disp), "icon": "⏳"},
    ])

    st.divider()

    filtro_estado = st.radio("Mostrar", ["Todos", "Solo disponibles", "Solo pendientes"], horizontal=True)

    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        filtro_texto = st.text_input("Buscar por nombre o descripción", "")
    with fc2:
        tipos_disp = sorted({t for _, t, _ in loaders.CATALOGO.values()})
        filtro_tipo = st.multiselect("Tipo de dato", tipos_disp)
    with fc3:
        fuentes_disp = sorted({f for _, _, f in loaders.CATALOGO.values()})
        filtro_fuente = st.multiselect("Fuente", fuentes_disp)

    for dataset, (nombre, tipo, fuente) in loaders.CATALOGO.items():
        esta = dataset in disponibles
        if filtro_estado == "Solo disponibles" and not esta:
            continue
        if filtro_estado == "Solo pendientes" and esta:
            continue
        if filtro_texto and filtro_texto.lower() not in nombre.lower() and filtro_texto.lower() not in dataset.lower():
            continue
        if filtro_tipo and tipo not in filtro_tipo:
            continue
        if filtro_fuente and fuente not in filtro_fuente:
            continue

        with st.expander(f"{'✅' if esta else '⏳'}  {nombre}  ·  `{dataset}`"):
            st.caption(f"Tipo: {tipo} · Fuente: {fuente}")
            if not esta:
                ui.sin_datos(dataset)
                continue

            meta = loaders.metadatos(dataset)
            ui.meta_caption(meta)
            with st.popover("Ver manifiesto completo (JSON)"):
                st.json(meta)

            kind = meta.get("kind")
            files = meta.get("files", {})

            if kind == "unavailable":
                ui.no_publicado(meta.get("note", "La fuente no tiene publicado este dataset ahora mismo."))

            elif kind == "vector":
                # Servir los bytes crudos del disco, no parsear+reserializar
                # (cargar_geojson/cargar_tabla decodifican todo el JSON/parquet
                # sólo para armar el botón de descarga): con capas de polígonos
                # grandes -- p.ej. municipios/alertas_idd/alertas_icv, ~1.100
                # features cada una -- eso tardaba >30s por dataset y hacía
                # esta página lentísima para cualquier visitante.
                c1, c2 = st.columns(2)
                with c1:
                    p = _ruta_existente(files, "parquet")
                    if p is not None:
                        boton_generico(p.read_bytes(), p.name, "application/octet-stream",
                                        "⬇️ Descargar tabla (Parquet)", key=f"cat_csv_{dataset}")
                with c2:
                    p = _ruta_existente(files, "geojson")
                    if p is not None:
                        boton_generico(p.read_bytes(), p.name, "application/geo+json",
                                        "⬇️ Descargar GeoJSON", key=f"cat_geo_{dataset}")
                if not files:
                    st.caption("Sin archivos en el manifiesto.")

            elif kind == "raster":
                p = _ruta_existente(files, "png")
                if p is not None:
                    boton_generico(p.read_bytes(), p.name, "image/png",
                                    "⬇️ Descargar imagen (PNG)", key=f"cat_png_{dataset}")

            elif kind == "table":
                # Mismo criterio que "vector": bytes crudos, sin pasar por
                # pandas sólo para armar la descarga.
                c1, c2 = st.columns(2)
                with c1:
                    p = _ruta_existente(files, "parquet")
                    if p is not None:
                        boton_generico(p.read_bytes(), p.name, "application/octet-stream",
                                        "⬇️ Descargar tabla (Parquet)", key=f"cat_csv_{dataset}")
                with c2:
                    p = _ruta_existente(files, "xlsx")
                    if p is not None:
                        boton_generico(
                            p.read_bytes(), p.name,
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            "⬇️ Descargar Excel", key=f"cat_xlsx_{dataset}",
                        )

            elif kind == "image_set":
                cols = st.columns(4)
                for i, (clave, ruta) in enumerate(files.items()):
                    p = Path(ruta)
                    if p.exists():
                        with cols[i % 4]:
                            boton_png(p, p.name, etiqueta=f"⬇️ {clave}", key=f"cat_imgset_{dataset}_{clave}")

            elif kind == "grid":
                p = _ruta_existente(files, "data")
                if p is not None:
                    boton_generico(
                        p.read_bytes(), p.name, "application/octet-stream",
                        f"⬇️ Descargar {p.name} ({meta.get('size_bytes', 0) / 1e6:.1f} MB)",
                        key=f"cat_grid_{dataset}",
                    )

            else:
                # alerta_diaria, amenaza_modelo y cualquier otro kind: lista
                # genérica de descarga (no se asume estructura fija).
                if meta.get("omitidos"):
                    st.caption(f"⚠️ {len(meta['omitidos'])} archivo(s) omitido(s) por tamaño (ver manifiesto).")
                for nombre_a, ruta in sorted(files.items()):
                    p = Path(ruta)
                    if p.exists():
                        boton_generico(p.read_bytes(), p.name, "application/octet-stream",
                                        f"⬇️ {nombre_a}", key=f"cat_generic_{dataset}_{nombre_a}")

    st.divider()
    st.subheader("Datos de referencia estáticos")
    st.caption(
        "No forman parte del cron de ingesta diaria: son insumos fijos que se actualizan por separado."
    )

    with st.expander("✅  Índices de riesgo municipal SNGRD  ·  `indices_riesgo_municipal`"):
        st.caption("Tipo: poligonos · Fuente: SNGRD (geometría simplificada para uso en el navegador)")
        geo_ref = loaders.cargar_referencia_indices_riesgo()
        if geo_ref is not None:
            boton_geojson(geo_ref, "indices_riesgo_municipal.geojson", key="cat_geo_indices_ref")

    with st.expander("✅  Emergencias históricas Sala de Crisis  ·  `sala_crisis`"):
        st.caption(
            "Tipo: tabla · Fuente: UNGRD Sala de Crisis. COMENTARIOS enmascarado (teléfonos/correos "
            "ocultos) porque la app es pública."
        )
        emerg = loaders.cargar_emergencias()
        if emerg is not None:
            boton_csv(emerg, "emergencias_sala_crisis.csv", key="cat_csv_sala_crisis")

with tab_api:
    st.subheader("Nivel base: archivo índice `api/datasets.json`")
    st.markdown(
        "Cada dataset del catálogo tiene una URL cruda (`raw.githubusercontent.com`) al último "
        "snapshot. No hace falta correr nada: es un `GET` normal.\n\n"
        "```python\n"
        "import requests\n"
        "idx = requests.get('.../api/datasets.json').json()\n"
        "url_csv = idx['datasets']['dane_divipola']['files']['parquet']\n"
        "```"
    )
    api_path = ROOT / "api" / "datasets.json"
    if api_path.exists():
        boton_generico(api_path.read_bytes(), "datasets.json", "application/json",
                        "⬇️ Descargar api/datasets.json", key="api_manifest")
        with st.popover("Ver api/datasets.json"):
            import json
            st.json(json.loads(api_path.read_text(encoding="utf-8")))
    else:
        st.info(
            "`api/datasets.json` se genera con `scripts/generar_api_datasets.py --repo usuario/repo` "
            "después de cada push (las URLs raw sólo sirven contenido ya commiteado)."
        )

    st.divider()
    st.subheader("Nivel avanzado: API consultable (Datasette)")
    st.markdown(
        "Las tablas municipales (índices de riesgo, temperatura, amenazas, DANE) también se "
        "consolidan en una base SQLite y se sirven con "
        "[Datasette](https://datasette.io/), que expone una API JSON con **filtros y consultas SQL** "
        "(no sólo el archivo completo). Se despliega aparte, en Hugging Face Spaces, porque "
        "Streamlit Community Cloud no puede correr un segundo servicio."
    )
    st.caption(
        "Enlace de la instancia de Datasette: pendiente de despliegue — se documentará aquí y en "
        "el README una vez publicada."
    )

ui.footer()
