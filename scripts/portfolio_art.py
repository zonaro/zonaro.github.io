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

# Monochrome outline icon set in the style of Lucide (ISC license):
# https://lucide.dev/license — compact path primitives are embedded so the
# dashboard and generated SVGs need no external fonts, network or JavaScript.
ICONS = {
    "code": '<path d="m18 16 4-4-4-4 M6 8l-4 4 4 4 M14.5 4l-5 16"/>',
    "game": '<line x1="6" y1="11" x2="10" y2="11"/><line x1="8" y1="9" x2="8" y2="13"/><line x1="15" y1="12" x2="15.01" y2="12"/><line x1="18" y1="10" x2="18.01" y2="10"/><path d="M17.32 5H6.68a4 4 0 0 0-3.978 3.59C2.6 9.42 2 14.46 2 16a3 3 0 0 0 3 3c1 0 1.5-.5 2-1l1.414-1.414A2 2 0 0 1 9.828 16h4.344a2 2 0 0 1 1.414.586L17 18c.5.5 1 1 2 1a3 3 0 0 0 3-3c0-1.545-.604-6.584-.685-7.258A4 4 0 0 0 17.32 5z"/>',
    "audio": '<path d="M3 14v-3a9 9 0 0 1 18 0v3"/><path d="M5 14h1a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2ZM18 14h1a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2Z"/>',
    "folder": '<path d="M10 10.5 8 13l2 2.5 M14 10.5l2 2.5-2 2.5"/><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2z"/>',
    "spark": '<path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3ZM19 17l.7 1.3L21 19l-1.3.7L19 21l-.7-1.3L17 19l1.3-.7L19 17ZM5 2l.8 1.8L8 4.5l-2.2.7L5 7l-.8-1.8L2 4.5l2.2-.7L5 2Z"/>',
    "wrench": '<path d="M14.7 6.3a5 5 0 0 0-6.4 6.4l-5.8 5.8a2 2 0 0 0 2.8 2.8l5.8-5.8a5 5 0 0 0 6.4-6.4l-3.1 3.1-3.7-.7-.7-3.7 3.1-3.1Z"/>',
    "globe": '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20 M2 12h20"/>',
    "phone": '<rect x="5" y="2" width="14" height="20" rx="2"/><path d="M12 18h.01"/>',
    "monitor": '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8 M12 17v4"/>',
    "database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5 M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/>',
    "palette": '<circle cx="13.5" cy="6.5" r=".5"/><circle cx="17.5" cy="10.5" r=".5"/><circle cx="8.5" cy="7.5" r=".5"/><circle cx="6.5" cy="12.5" r=".5"/><path d="M12 22a10 10 0 1 1 10-10 3.5 3.5 0 0 1-3.5 3.5H16a2 2 0 0 0-2 2 2 2 0 0 1-2 4.5Z"/>',
    "music": '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
    "book": '<path d="M12 7v14 M3 18V4.5A1.5 1.5 0 0 1 4.5 3H8a4 4 0 0 1 4 4 4 4 0 0 1 4-4h3.5A1.5 1.5 0 0 1 21 4.5V18h-5a4 4 0 0 0-4 3 4 4 0 0 0-4-3H3Z"/>',
    "bot": '<rect x="3" y="8" width="18" height="12" rx="3"/><path d="M12 8V4 M9 4h6 M7 13h.01 M17 13h.01 M9 17h6 M1 12v4 M23 12v4"/>',
    "rocket": '<path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91-.78-.78-2.07-.8-2.91-.09ZM12 15l-3-3c.53-2.37 1.6-4.8 3.5-6.7C16.5 1.3 22 2 22 2s.7 5.5-3.3 9.5C16.8 13.4 14.37 14.47 12 15Z M9 12H4s0-3 1-4c1-1 4-1 4-1 M12 15v5s3 0 4-1c1-1 1-4 1-4"/><circle cx="16" cy="8" r="1.5"/>',
    "cloud": '<path d="M20 16.6a4.5 4.5 0 0 0-1.5-8.7A7 7 0 0 0 5.3 9.6 4.8 4.8 0 0 0 6 19h13a3 3 0 0 0 1-5.8"/>',
    "terminal": '<rect x="2" y="3" width="20" height="18" rx="2"/><path d="m7 9 3 3-3 3 M13 15h4"/>',
    "package": '<path d="m12 2 9 5v10l-9 5-9-5V7l9-5ZM3 7l9 5 9-5 M12 12v10 M7.5 4.5l9 5"/>',
    "heart": '<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78L12 21.23l8.84-8.84a5.5 5.5 0 0 0 0-7.78Z"/>',
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
    if style not in {"orbits", "grid", "waves"} or icon not in {"auto", "letter", *ICONS}:
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

    if icon == "letter":
        icon_svg = f'<text x="0" y="55" font-size="195" font-weight="800" font-family="system-ui,sans-serif" text-anchor="middle" fill="#ffffff" stroke="none">{html.escape(name[:1].upper())}</text>'
        icon_group = f'<g transform="translate(640 302)">{icon_svg}</g>'
    else:
        icon_group = (f'<g transform="translate(500 162) scale(11.7)" fill="none" stroke="#ffffff" '
                      f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{ICONS[icon]}</g>')
    decoration = {
        "orbits": '<ellipse cx="640" cy="325" rx="370" ry="188" fill="none" stroke="#ffffff" stroke-opacity=".15" transform="rotate(-25 640 325)"/><ellipse cx="640" cy="325" rx="420" ry="155" fill="none" stroke="#ffffff" stroke-opacity=".12" transform="rotate(27 640 325)"/>',
        "grid": '<path d="M0 160H1280 M0 320H1280 M0 480H1280 M160 0V640 M320 0V640 M480 0V640 M640 0V640 M800 0V640 M960 0V640 M1120 0V640" fill="none" stroke="#ffffff" stroke-opacity=".09" stroke-width="2"/>',
        "waves": '<path d="M-100 490 Q240 210 570 480 T1380 430 M-100 560 Q280 280 610 550 T1380 490" fill="none" stroke="#ffffff" stroke-opacity=".13" stroke-width="24"/>',
    }[style]
    return f'''<svg xmlns="{SVG_NS}" width="1280" height="640" viewBox="0 0 1280 640" role="img" aria-label="Arte de capa de {html.escape(name, quote=True)}">
<defs><linearGradient id="background" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stop-color="{background}"/><stop offset="1" stop-color="#100d1a"/></linearGradient><radialGradient id="glow"><stop offset="0" stop-color="{accent}" stop-opacity=".68"/><stop offset="1" stop-color="{accent}" stop-opacity="0"/></radialGradient></defs>
<rect width="1280" height="640" fill="url(#background)"/><ellipse cx="640" cy="320" rx="525" ry="340" fill="url(#glow)"/>
{decoration}<circle cx="640" cy="315" r="166" fill="#11101c" opacity=".55"/><circle cx="640" cy="315" r="164" fill="none" stroke="{accent}" stroke-width="4" opacity=".65"/>
{icon_group}<text x="640" y="580" fill="#ffffff" font-family="system-ui,sans-serif" font-weight="750" font-size="38" text-anchor="middle" letter-spacing="4">{html.escape(name[:35].upper())}</text></svg>'''


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
