"""
pages/6_Metodologia_y_fuentes.py
====================================
Documentación transparente: fuentes, claves de cruce, cómo se producen los
snapshots, reglas de "no inventar" y limitaciones conocidas. Escrita para
que cualquier usuario técnico pueda auditar de dónde sale cada dato.
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import ui  # noqa: E402

ui.header("Metodología y fuentes", "Cómo se producen, cruzan y publican los datos de este portal.")

st.subheader("1. Fuentes de datos")
st.markdown(
    "| Fuente | Qué aporta | Cómo se obtiene |\n"
    "|---|---|---|\n"
    "| **IDEAM — ArcGIS OSPA** (`visualizador.ideam.gov.co`) | Estaciones de precipitación/temperatura, "
    "alertas hidrológicas, capas de amenaza (deslizamientos/incendios), pronóstico y acumulados ráster | "
    "Consultas REST (`/query`, `/export`) paginadas, GeoJSON/PNG |\n"
    "| **IDEAM — BART** (`bart.ideam.gov.co/ospa/Alertas/`) | Descensos de temperatura, granizo, índice de "
    "calor, temperatura municipal, modelos de amenaza (deslizamientos/incendios/hidrología), hidroestimador satelital | "
    "Crawler recursivo de directorios Apache (`bart_alertas.py`) |\n"
    "| **IDEAM — WRF/GFS y CPT** (`bart.ideam.gov.co/wrfideam/`) | Grillas de modelo (NetCDF/GeoTIFF/GRIB2) y "
    "predicción estacional (imágenes CPT, 6 meses) | Listado de directorio + verificación HEAD por URL |\n"
    "| **DANE** (`geoportal.dane.gov.co`) | DIVIPOLA oficial: nombres/coordenadas de los 1.122 municipios | "
    "Descarga directa del Excel oficial (hoja `Municipios`) |\n"
    "| **UNGRD — Sala de Crisis** | Emergencias históricas por municipio (conteo, familias, personas, muertos) | "
    "Archivo interno, `COMENTARIOS` enmascarado antes de publicar |\n"
    "| **SNGRD — índices de riesgo municipal** | Universo base de 1.122 municipios con geometría de polígono | "
    "Capa de referencia estática, geometría simplificada para el navegador |\n"
)

st.subheader("2. Cómo se cruzan los datos (DIVIPOLA)")
st.markdown(
    "El universo base de la página **Consulta y cruce municipal** son los 1.122 municipios de la "
    "capa de índices de riesgo SNGRD — es la única fuente con geometría de polígono utilizable "
    "para el mapa coroplético. Cada fuente adicional se cruza sobre ese universo con un "
    "**left-join por código DIVIPOLA**, normalizado siempre a texto de 5 dígitos "
    "(`str(codigo).zfill(5)`, tolerante a artefactos de float tipo `'5001.0'`).\n\n"
    "**Un municipio ausente en una fuente queda con valor vacío (`NaN`) en las columnas de esa "
    "fuente — nunca se rellena con estimaciones.** El reporte completo de no-cruce (qué municipio "
    "no aparece en qué fuente) es visible y descargable en la propia página de cruce, y se guarda "
    "en `data_lake/_diagnostico/divipola_no_cruza.csv`."
)

st.subheader("3. Cómo se producen los snapshots")
st.markdown(
    "Un proceso automático (cron de GitHub Actions) corre los extractores periódicamente y "
    "escribe cada snapshot en `data_lake/{dataset}/dt=YYYY-MM-DD/...`, con un puntero "
    "`latest.json` para lectura inmediata. **El portal nunca consulta IDEAM/DANE en vivo**: "
    "siempre lee el último snapshot, y cada sección muestra su fecha de actualización "
    "(`Actualizado: ...`) junto a los datos.\n\n"
    "Los archivos se deduplican por hash de contenido: si una fuente no cambió desde la última "
    "corrida, no se vuelve a escribir (el histórico en `data_lake/` sólo crece cuando hay un "
    "cambio real)."
)

st.subheader("4. Alertas diarias: por qué nunca se decide por la fecha de una carpeta")
st.markdown(
    "El árbol `/ospa/Alertas/` de IDEAM organiza varias categorías por fecha "
    "(`Categoria/AAAAMMDD/...`), pero **la fecha que muestra un listado de carpeta refleja su "
    "último cambio estructural, no necesariamente el contenido más reciente** — se confirmó en "
    "vivo que la carpeta `modelos/` puede mostrar una fecha de más de un año atrás mientras que "
    "`modelos/deslizamientos/ultimo/` tiene archivos de hoy. Por eso `bart_alertas.py`:\n\n"
    "- Nunca decide entrar o no a una carpeta por su fecha: siempre baja hasta el nivel de archivo.\n"
    "- Para categorías por fecha, toma la subcarpeta **`AAAAMMDD` más reciente que sí tenga "
    "archivos** (algunas fechas quedan vacías, p. ej. sin evento ese día) — es consulta del dato "
    "vigente, no una réplica del histórico completo.\n"
    "- Para `modelos/*/ultimo/`, usa esa carpeta tal cual: es, por convención de la fuente, donde "
    "vive el dato vigente."
)

st.subheader("5. Qué se omite y por qué")
st.markdown(
    "Algunos productos rasterizados de muy alta resolución (p. ej. el downscaling nacional a 30m "
    "de temperatura, o los shapefiles completos de índice de calor) pesan varios cientos de MB o "
    "más por corrida — inviable para un repositorio de git (límite duro de GitHub: 100MB por "
    "archivo) y para una ingesta diaria sostenible. `bart_alertas.py` omite estos archivos de forma "
    "**auditable**: quedan registrados en el manifiesto del dataset (campo `omitidos`, con su URL "
    "de origen) en vez de descargarse o de sustituirse por una versión reducida inventada."
)

st.subheader("6. Datos pendientes (nunca inventados)")
st.markdown(
    "La caracterización municipal DANE (hogares, % rural, % étnico, estrato predominante) no tiene "
    "todavía una fuente nacional verificada con cobertura ≥1.100 municipios (el dataset Socrata "
    "originalmente referenciado, `64cq-xb2k`, está dado de baja; el Geoportal DANE no publica un "
    "archivo nacional equivalente). Estas columnas existen en el cruce municipal — para no romper "
    "el join — pero quedan vacías, marcadas explícitamente como pendientes, hasta contar con una "
    "fuente verificada."
)

st.subheader("7. Limitaciones conocidas")
st.markdown(
    "- El servidor ArcGIS de IDEAM presenta errores 500 intermitentes en algunas capas "
    "(reintentos automáticos con backoff; si persisten, esa capa queda sin snapshot nuevo hasta "
    "la siguiente corrida — el resto de datasets no se ve afectado).\n"
    "- Las grillas WRF/GFS no siempre están publicadas en el momento de la corrida del extractor.\n"
    "- El CPT no siempre publica las 3 variables (precipitación/temperatura/viento) en el mismo "
    "ciclo; cuando falta una, el portal lo muestra como *\"no publicado\"* (verificado con HEAD), "
    "no como error.\n"
    "- Todos los datos de pronóstico y observación reciente son **preliminares** y están sujetos a "
    "revisión y control de calidad por las entidades fuente. Este portal no reemplaza los "
    "boletines oficiales de IDEAM ni las alertas de UNGRD."
)

ui.footer()
