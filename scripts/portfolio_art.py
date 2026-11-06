"""Deterministic SVG covers and a strict sanitizer for local dashboard uploads."""

from __future__ import annotations

import hashlib
import html
import re
from xml.etree import ElementTree as ET


SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
SAFE_COLOR = re.compile(r"^(?:#[0-9a-fA-F]{3,8}|none|transparent|currentColor|url\(#[A-Za-z_][\w.-]*\))$")
SAFE_TAGS = {
    "svg", "g", "defs", "linearGradient", "radialGradient", "stop", "rect", "circle",
    "ellipse", "path", "polygon", "polyline", "line", "text", "tspan",
}
SAFE_ATTRS = {
    "xmlns", "viewBox", "width", "height", "preserveAspectRatio", "id", "fill", "stroke",
    "stroke-width", "stroke-linecap", "stroke-linejoin", "stroke-dasharray", "stroke-opacity", "opacity", "d",
    "rx", "ry", "transform", "x", "y", "x1", "x2", "y1", "y2", "cx", "cy",
    "r", "points", "offset", "stop-color", "stop-opacity", "font-family", "font-size",
    "font-weight", "text-anchor", "letter-spacing", "role", "aria-label",
}


def default_colors(name: str) -> tuple[str, str]:
    palettes = [
        ("#31154f", "#c65dff"), ("#0b344b", "#40c9fb"),
        ("#352042", "#ff7294"), ("#103b37", "#69e6b9"),
        ("#352319", "#ffb65c"), ("#20284d", "#8c9dff"),
    ]
    return palettes[hashlib.sha256(name.casefold().encode()).digest()[0] % len(palettes)]


def make_cover_svg(name: str, style: str = "orbits", icon: str = "auto",
                   background: str | None = None, accent: str | None = None) -> str:
    if style not in {"orbits", "grid", "waves"} or icon not in {
        "auto", "code", "game", "audio", "folder", "spark", "letter",
    }:
        raise ValueError("Modelo ou símbolo inválido")
    default_bg, default_accent = default_colors(name)
    background = background or default_bg
    accent = accent or default_accent
    if not HEX.fullmatch(background) or not HEX.fullmatch(accent):
        raise ValueError("Use cores no formato hexadecimal #RRGGBB")
    if icon == "auto":
        lower = name.casefold()
        icon = ("game" if any(x in lower for x in ("jolven", "game", "launcher", "steam"))
                else "audio" if any(x in lower for x in ("sound", "music", "beat", "navox"))
                else "folder" if any(x in lower for x in ("nautilus", "files", "notes"))
                else "code")

    path = {
        "code": '<path d="m-72 -22 -42 42 42 42 M72 -22 l42 42 -42 42 M20 -80 -42 200"/>',
        "game": '<path d="M-103 -32 Q-125 -32 -134 0 L-154 66 Q-162 100 -132 100 Q-111 100 -81 66 L81 66 Q111 100 132 100 Q162 100 154 66 L134 0 Q125 -32 103 -32Z"/><path d="M-87 2v54 M-114 29h54"/><circle cx="90" cy="18" r="8"/><circle cx="113" cy="41" r="8"/>',
        "audio": '<path d="M-126 -9 Q-126 -126 0 -126 Q126 -126 126 -9 M-125 -18 h30 v95 h-30 Q-155 77 -155 46 v-34 Q-155 -18 -125 -18Z M95 -18h30 Q155 -18 155 12v34 Q155 77 125 77H95Z"/><path d="M-30 -30 v80 M0 -66 v152 M30 -30 v80"/>',
        "folder": '<path d="M-144 -68 H-50 L-19 -38 H132 Q148 -38 148 -22 V80 Q148 98 130 98 H-130 Q-148 98 -148 80 V-50 Q-148 -68 -130 -68Z"/><path d="M-145 -9 H145"/>',
        "spark": '<path d="M0 -143 L35 -36 142 0 35 36 0 143 -35 36 -142 0 -35 -36Z"/>',
    }
    if icon == "letter":
        icon_svg = f'<text x="0" y="55" font-size="195" font-weight="800" font-family="system-ui,sans-serif" text-anchor="middle" fill="#ffffff" stroke="none">{html.escape(name[:1].upper())}</text>'
    else:
        icon_svg = f'<g fill="none" stroke="#ffffff" stroke-width="15" stroke-linecap="round" stroke-linejoin="round">{path[icon]}</g>'
    decoration = {
        "orbits": '<ellipse cx="640" cy="325" rx="370" ry="188" fill="none" stroke="#ffffff" stroke-opacity=".15" transform="rotate(-25 640 325)"/><ellipse cx="640" cy="325" rx="420" ry="155" fill="none" stroke="#ffffff" stroke-opacity=".12" transform="rotate(27 640 325)"/>',
        "grid": '<path d="M0 160H1280 M0 320H1280 M0 480H1280 M160 0V640 M320 0V640 M480 0V640 M640 0V640 M800 0V640 M960 0V640 M1120 0V640" fill="none" stroke="#ffffff" stroke-opacity=".09" stroke-width="2"/>',
        "waves": '<path d="M-100 490 Q240 210 570 480 T1380 430 M-100 560 Q280 280 610 550 T1380 490" fill="none" stroke="#ffffff" stroke-opacity=".13" stroke-width="24"/>',
    }[style]
    return f'''<svg xmlns="{SVG_NS}" width="1280" height="640" viewBox="0 0 1280 640" role="img" aria-label="Arte de capa de {html.escape(name, quote=True)}">
<defs><linearGradient id="background" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stop-color="{background}"/><stop offset="1" stop-color="#100d1a"/></linearGradient><radialGradient id="glow"><stop offset="0" stop-color="{accent}" stop-opacity=".68"/><stop offset="1" stop-color="{accent}" stop-opacity="0"/></radialGradient></defs>
<rect width="1280" height="640" fill="url(#background)"/><ellipse cx="640" cy="320" rx="525" ry="340" fill="url(#glow)"/>
{decoration}<circle cx="640" cy="315" r="166" fill="#11101c" opacity=".55"/><circle cx="640" cy="315" r="164" fill="none" stroke="{accent}" stroke-width="4" opacity=".65"/>
<g transform="translate(640 302)">{icon_svg}</g><text x="640" y="580" fill="#ffffff" font-family="system-ui,sans-serif" font-weight="750" font-size="38" text-anchor="middle" letter-spacing="4">{html.escape(name[:35].upper())}</text></svg>'''


def sanitize_svg(source: str) -> str:
    if not isinstance(source, str) or len(source.encode("utf-8")) > 100_000:
        raise ValueError("O SVG deve ter no máximo 100 KB")
    if any(token in source.upper() for token in ("<!DOCTYPE", "<!ENTITY", "<?XML-STYLESHEET")):
        raise ValueError("SVG não pode conter DTD, entidades ou folhas de estilo externas")
    try:
        root = ET.fromstring(source)
    except ET.ParseError as exc:
        raise ValueError("Arquivo SVG inválido") from exc
    if root.tag != f"{{{SVG_NS}}}svg":
        raise ValueError("O arquivo precisa ser um SVG com namespace correto")
    elements = 0

    def visit(element: ET.Element, depth: int) -> None:
        nonlocal elements
        elements += 1
        if depth > 24 or elements > 400:
            raise ValueError("SVG muito complexo")
        if element.tag not in {f"{{{SVG_NS}}}{tag}" for tag in SAFE_TAGS}:
            raise ValueError("SVG contém elemento não permitido")
        if element.text and element.tag not in {f"{{{SVG_NS}}}text", f"{{{SVG_NS}}}tspan"} and element.text.strip():
            raise ValueError("Texto fora de elemento de texto não é permitido")
        for attr, value in element.attrib.items():
            if attr not in SAFE_ATTRS:
                raise ValueError(f"SVG contém atributo não permitido: {attr}")
            if attr in {"fill", "stroke", "stop-color"} and not SAFE_COLOR.fullmatch(value):
                raise ValueError("Cor ou recurso externo não permitido")
            if "url(" in value.lower() and not re.fullmatch(r"url\(#[A-Za-z_][\w.-]*\)", value):
                raise ValueError("Referências externas não são permitidas")
        for child in element:
            visit(child, depth + 1)

    visit(root, 0)
    return ET.tostring(root, encoding="unicode") + "\n"
