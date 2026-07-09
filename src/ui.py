"""
src/ui.py
=========
Componentes de marca UNGRD: paleta institucional (extraída del logo,
`assets/LOGO_UNGRD.png`), CSS global, encabezado, pie de página y tarjetas
KPI. Se reutilizan en todas las páginas para que la distribución y el
estilo sean consistentes en todo el portal.

Nota de alcance (Portal de Datos SNIGRD): no incluye el semáforo de fase
ENSO de la v1 (visor ENSO) — este portal es de consulta y cruce de datos,
no de análisis interpretativo.
"""
from __future__ import annotations

import base64
import html
from pathlib import Path
from typing import Optional

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
LOGO_PATH = ROOT / "assets" / "LOGO_UNGRD.png"


@st.cache_data(show_spinner=False)
def _logo_base64() -> str:
    return base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")

# --------------------------------------------------------------------------- #
# Paleta institucional UNGRD — extraída por muestreo de píxeles del logo
# (no inventada). Colores de nivel de amenaza/riesgo: escala semáforo accesible.
# --------------------------------------------------------------------------- #
COLORS = {
    "navy": "#1F3460",       # azul institucional (dominante en el logo)
    "navy_dark": "#16264A",  # variante oscura (sidebar/hover)
    "gold": "#FECC17",       # amarillo/dorado institucional (mano del logo)
    "red": "#D80C28",        # rojo institucional (franja del logo)
    "white": "#FFFFFF",
    "gray_bg": "#F2F4F8",
    "gray_text": "#5B6472",
}

NIVEL_COLOR = {
    "alto": "#D7263D",
    "alta": "#D7263D",
    "medio": "#F4A83D",
    "media": "#F4A83D",
    "bajo": "#2E8B57",
    "baja": "#2E8B57",
    "sin dato": "#7A7F87",  # mas oscuro que el gris claro original: mejor contraste con texto blanco
}

KPI_PALETTE = [
    ("#E7F0FA", "#1F3460"),  # azul
    ("#E9F7EF", "#1E8449"),  # verde
    ("#FDEDEC", "#C0392B"),  # rojo
    ("#FEF6E0", "#B7860B"),  # ámbar
    ("#F1EAFB", "#6C3FBF"),  # morado
    ("#EAF6F8", "#117A8B"),  # cian
]


def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        .stApp {{ background-color: {COLORS['white']}; }}

        [data-testid="stSidebar"] {{
            background-color: {COLORS['navy']};
        }}
        [data-testid="stSidebar"] * {{
            color: {COLORS['white']} !important;
        }}
        /* la cajita de busqueda de paginas tiene fondo blanco: el texto
           blanco de la regla de arriba la deja ilegible (blanco sobre
           blanco). Forzamos texto oscuro ahi y en cualquier input/desplegable
           con fondo claro dentro del sidebar. */
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] [role="option"],
        [data-testid="stSidebar"] [role="listbox"],
        [data-testid="stSidebarNav"] [data-testid="stSidebarNavSearchInput"] {{
            color: {COLORS['navy']} !important;
        }}
        [data-testid="stSidebar"] input::placeholder {{
            color: {COLORS['gray_text']} !important;
            opacity: 1;
        }}
        [data-testid="stSidebarNav"] a {{
            border-radius: 8px;
            margin: 2px 8px;
        }}
        [data-testid="stSidebarNav"] a:hover {{
            background-color: {COLORS['navy_dark']};
        }}
        [data-testid="stSidebarNav"] a[aria-current="page"] {{
            background-color: {COLORS['white']};
        }}
        /* el texto/icono del item activo puede estar en cualquier hijo (span,
           p, div...) segun la version de Streamlit: cubrimos todos los
           descendientes, no solo "span", para que nunca quede blanco sobre
           blanco. */
        [data-testid="stSidebarNav"] a[aria-current="page"],
        [data-testid="stSidebarNav"] a[aria-current="page"] * {{
            color: {COLORS['navy']} !important;
            font-weight: 700;
        }}

        [data-testid="stSidebarContent"] {{
            display: flex;
            flex-direction: column;
        }}
        [data-testid="stSidebarContent"] div:has(> .ungrd-sidebar-brand) {{
            order: -1;
        }}

        .ungrd-sidebar-brand {{
            background-color: {COLORS['white']};
            border-radius: 12px;
            padding: 10px 14px;
            margin: 6px 8px 2px 8px;
        }}
        .ungrd-sidebar-title {{
            color: {COLORS['white']} !important;
            font-weight: 800;
            font-size: 1.15rem;
            line-height: 1.35rem;
            text-align: center;
            margin: 10px 8px 18px 8px;
        }}

        .ungrd-header-title {{
            color: {COLORS['navy']};
            font-weight: 800;
            font-size: clamp(1.4rem, 5vw, 2.1rem);
            margin-bottom: 0.15rem;
        }}
        .ungrd-header-sub {{
            color: {COLORS['gray_text']};
            font-size: clamp(0.86rem, 2.6vw, 0.98rem);
            line-height: 1.45rem;
            margin-bottom: 1.1rem;
        }}
        .ungrd-header-sub b {{ color: {COLORS['navy']}; }}

        .ungrd-kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
            gap: 12px;
            margin-bottom: 0.6rem;
        }}
        .ungrd-kpi-card {{
            border-radius: 14px;
            padding: 14px 16px;
            height: 100%;
        }}
        .ungrd-kpi-icon {{ font-size: 1.3rem; }}
        .ungrd-kpi-value {{ font-size: clamp(1.35rem, 4.5vw, 1.7rem); font-weight: 800; line-height: 1.9rem; }}
        .ungrd-kpi-label {{ font-size: 0.82rem; font-weight: 600; opacity: 0.85; }}
        .ungrd-kpi-sub {{ font-size: 0.78rem; opacity: 0.7; }}

        /* pantallas angostas: 2x2 en vez de 1x4 (pedido explicito), menos
           relleno, botones mas altos para que el dedo los toque comodo */
        @media (max-width: 640px) {{
            .ungrd-kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
        }}
        @media (max-width: 480px) {{
            .ungrd-kpi-card {{ padding: 10px 12px; }}
            .ungrd-sidebar-brand {{ margin: 4px 6px 2px 6px; padding: 8px 10px; }}
            .block-container {{ padding-left: 1rem; padding-right: 1rem; }}
            button[kind], .stDownloadButton button {{ min-height: 2.6rem; }}
        }}
        iframe {{ max-width: 100%; }}

        .ungrd-badge {{
            display: inline-block; padding: 3px 12px; border-radius: 999px;
            font-weight: 700; font-size: 0.82rem; color: white;
        }}

        .ungrd-footer {{
            margin-top: 2.2rem; padding-top: 0.8rem;
            border-top: 1px solid #E3E6EC;
            color: {COLORS['gray_text']}; font-size: 0.78rem; line-height: 1.35rem;
        }}
        .ungrd-meta {{
            color: {COLORS['gray_text']}; font-size: 0.78rem; margin-top: -6px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def sidebar_brand() -> None:
    """Tarjeta blanca con el logo + nombre del portal, arriba del menú. Se
    llama una sola vez, desde app.py."""
    inject_css()
    with st.sidebar:
        img_html = (
            f'<img src="data:image/png;base64,{_logo_base64()}" style="width:100%;" />'
            if LOGO_PATH.exists() else ""
        )
        st.markdown(
            f"""
            <div class="ungrd-sidebar-brand">{img_html}</div>
            <div class="ungrd-sidebar-title">Portal de Datos<br/>SNIGRD</div>
            """,
            unsafe_allow_html=True,
        )


def header(titulo: str, subtitulo_html: str = "") -> None:
    inject_css()
    st.markdown(f"<div class='ungrd-header-title'>{titulo}</div>", unsafe_allow_html=True)
    if subtitulo_html:
        st.markdown(f"<div class='ungrd-header-sub'>{subtitulo_html}</div>", unsafe_allow_html=True)


def footer() -> None:
    st.markdown(
        f"""
        <div class="ungrd-footer">
        <b>Fuentes:</b> IDEAM (OSPA / BART / WRF-GFS) y DANE (DIVIPOLA).
        Los datos de pronóstico y observación reciente son <b>preliminares</b> y están
        sujetos a revisión y control de calidad por parte de las entidades fuente.
        Este portal es de consulta, cruce y descarga de datos — no reemplaza los
        boletines oficiales de IDEAM ni las alertas de UNGRD.<br/>
        Subdirección para el Conocimiento del Riesgo — Unidad Nacional para la Gestión del Riesgo de Desastres (UNGRD).
        </div>
        """,
        unsafe_allow_html=True,
    )


def kpi_card(label: str, value: str, sub: str = "", icon: str = "📊", palette_idx: int = 0) -> str:
    # value/sub suelen traer texto derivado de datos externos (nombre de
    # estación, municipio...): se escapan antes de meterlos en HTML crudo.
    bg, fg = KPI_PALETTE[palette_idx % len(KPI_PALETTE)]
    value_esc = html.escape(str(value))
    label_esc = html.escape(str(label))
    sub_esc = html.escape(str(sub)) if sub else ""
    sub_html = f'<div class="ungrd-kpi-sub">{sub_esc}</div>' if sub_esc else ""
    # Todo en una sola línea, sin indentación: HTML indentado dentro de un
    # bloque multilínea lo interpreta Markdown como un code block ("4 espacios
    # = código"), no como HTML — dejaba las tarjetas 2+ mostrando el <div>
    # crudo en vez de renderizarlo (bug real, visto en captura móvil en v1).
    return (
        f'<div class="ungrd-kpi-card" style="background-color:{bg}; color:{fg};">'
        f'<div class="ungrd-kpi-icon">{icon}</div>'
        f'<div class="ungrd-kpi-value">{value_esc}</div>'
        f'<div class="ungrd-kpi-label">{label_esc}</div>'
        f'{sub_html}</div>'
    )


def kpi_row(cards: list[dict]) -> None:
    """cards: [{label, value, sub, icon}], se colorean en secuencia con KPI_PALETTE.

    Grid CSS (no st.columns): st.columns apila a 1 por fila en móvil, pero el
    requerimiento pide 2x2 en pantallas angostas en vez de 1x4."""
    inject_css()
    items = "".join(
        kpi_card(c.get("label", ""), c.get("value", "—"), c.get("sub", ""), c.get("icon", "📊"), i)
        for i, c in enumerate(cards)
    )
    st.markdown(f'<div class="ungrd-kpi-grid">{items}</div>', unsafe_allow_html=True)


def badge(texto: str, color: str) -> str:
    return f'<span class="ungrd-badge" style="background-color:{color};">{html.escape(str(texto))}</span>'


def meta_caption(meta: Optional[dict]) -> None:
    """Caption estándar 'Actualizado: ... · Fuente: ...' para cualquier dataset."""
    if meta is None:
        st.caption("Sin snapshot disponible todavía.")
        return
    st.caption(
        f"Actualizado: {meta.get('updated_at','—')} · "
        f"Fuente: {meta.get('descripcion', meta.get('source_url','IDEAM'))}"
    )


def sin_datos(dataset: str, detalle: str = "") -> None:
    st.warning(
        f"No hay snapshot disponible para **{dataset}** todavía. "
        "El extractor lo generará en la próxima corrida programada (o corre el script manualmente). "
        + detalle
    )


def no_publicado(nota: str) -> None:
    """Para datasets que el extractor SÍ verificó (con HEAD) y confirmó que la
    fuente no los tiene publicados ahora mismo — distinto de 'nunca se corrió
    el extractor'. Mensaje neutro, no de error."""
    st.info(f"ℹ️ {nota}")
