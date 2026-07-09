"""
src/maps.py
===========
Helpers de mapas con folium + streamlit-folium. Deliberadamente NO usa
geopandas/leafmap (rompen el build en Streamlit Community Cloud); folium
acepta el dict GeoJSON tal cual lo devuelven los loaders de src/loaders.py.
"""
from __future__ import annotations

from typing import Callable, Optional

import folium
from branca.element import MacroElement, Template
from streamlit_folium import st_folium

from src.ui import COLORS

COLOMBIA_CENTER = [4.6, -73.0]
COLOMBIA_ZOOM = 5


def mapa_base(center: list[float] | None = None, zoom: int = COLOMBIA_ZOOM) -> folium.Map:
    return folium.Map(
        location=center or COLOMBIA_CENTER,
        zoom_start=zoom,
        tiles="CartoDB positron",
        control_scale=True,
    )


def capa_vector_coloreada(
    m: folium.Map,
    geojson: dict,
    color_field: str,
    color_map: dict[str, str],
    tooltip_fields: list[str],
    tooltip_aliases: Optional[list[str]] = None,
    nombre: str = "capa",
    color_defecto: str = "#B0B0B0",
) -> folium.GeoJson:
    """Capa vectorial (polígonos) coloreada categóricamente por `color_field`."""

    def _style(feature):
        val = feature["properties"].get(color_field)
        return {
            "fillColor": color_map.get(val, color_defecto),
            "color": "#5B6472",
            "weight": 0.6,
            "fillOpacity": 0.75,
        }

    def _highlight(_feature):
        return {"weight": 2, "color": COLORS["navy"], "fillOpacity": 0.9}

    layer = folium.GeoJson(
        geojson,
        name=nombre,
        style_function=_style,
        highlight_function=_highlight,
        tooltip=folium.GeoJsonTooltip(
            fields=tooltip_fields,
            aliases=tooltip_aliases or tooltip_fields,
            sticky=True,
        ),
    )
    layer.add_to(m)
    return layer


def capa_puntos(
    m: folium.Map,
    geojson: dict,
    tooltip_fields: list[str],
    tooltip_aliases: Optional[list[str]] = None,
    nombre: str = "estaciones",
    color: str = "#1F3460",
    radio: int = 4,
) -> folium.FeatureGroup:
    """Estaciones puntuales (precipitación/temperatura) como círculos."""
    grupo = folium.FeatureGroup(name=nombre)
    for feat in geojson.get("features", []):
        geom = feat.get("geometry") or {}
        if geom.get("type") != "Point":
            continue
        lon, lat = geom["coordinates"][:2]
        props = feat.get("properties", {})
        tooltip_txt = "<br>".join(
            f"<b>{alias}:</b> {props.get(f, '—')}"
            for f, alias in zip(tooltip_fields, tooltip_aliases or tooltip_fields)
        )
        folium.CircleMarker(
            location=[lat, lon],
            radius=radio,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.75,
            weight=1,
            tooltip=tooltip_txt,
        ).add_to(grupo)
    grupo.add_to(m)
    return grupo


def capa_raster(m: folium.Map, png_path: str, bounds: list, nombre: str = "raster", opacidad: float = 0.7):
    if not bounds:
        return None
    overlay = folium.raster_layers.ImageOverlay(
        image=png_path,
        bounds=bounds,
        opacity=opacidad,
        name=nombre,
        interactive=True,
        cross_origin=False,
    )
    overlay.add_to(m)
    return overlay


_LEGEND_TEMPLATE = """
{% macro html(this, kwargs) %}
<div style="position: fixed; bottom: 24px; left: 24px; z-index:9999;
            background: white; padding: 10px 14px; border-radius: 10px;
            box-shadow: 0 1px 6px rgba(0,0,0,0.25); font-size: 12.5px; color:#1A1A2E;">
  <b>{{ this.titulo }}</b><br/>
  {% for color, label in this.items %}
    <div style="margin-top:4px;">
      <span style="display:inline-block;width:12px;height:12px;border-radius:3px;
                   background:{{ color }};margin-right:6px;"></span>{{ label }}
    </div>
  {% endfor %}
</div>
{% endmacro %}
"""


class Leyenda(MacroElement):
    def __init__(self, titulo: str, items: list[tuple[str, str]]):
        super().__init__()
        self._template = Template(_LEGEND_TEMPLATE)
        self.titulo = titulo
        self.items = items


def agregar_leyenda(m: folium.Map, titulo: str, items: list[tuple[str, str]]) -> None:
    m.get_root().add_child(Leyenda(titulo, items))


def mostrar_mapa(m: folium.Map, key: str, height: int = 520, con_capas: bool = False):
    if con_capas:
        folium.LayerControl(collapsed=True).add_to(m)
    return st_folium(m, height=height, use_container_width=True, key=key,
                      returned_objects=[])
