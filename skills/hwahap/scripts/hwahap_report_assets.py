"""Load pinned static report assets."""

import hashlib
from pathlib import Path

STYLE_SHA256 = "db7acdf9f00b69031f8e1dfce46180fd7fea61504963a45a45817687519d68ac"
META_STATIC = (
    '<meta charset="utf-8">',
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    '<meta name="color-scheme" content="light dark">',
    '<meta name="material-design-system" content="Material Design 3">',
    '<meta name="material-theme-source" content="Material Design 3 official guidance">',
    '<meta name="color-theme-name" content="Icy Blue">',
    '<meta name="color-theme-seed" content="#C2E7FF">',
    '<meta name="color-theme-source" content="https://coolors.co/tailwind/c2e7ff">',
    '<meta name="material-foundations-pages" content="68">',
    '<meta name="material-source-url" content="https://m3.material.io/foundations">',
    '<meta name="material-spec-snapshot" content="2026-08-29">',
    '<meta name="hwahap-redaction-policy" '
    'content="credentials,authorization,bearer,api-key,private-key,password; bounded">',
)


def load_style() -> str:
    path = Path(__file__).parents[1] / "assets" / "report" / "style.css"
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != STYLE_SHA256:
        raise ImportError("report style dependency unavailable")
    return '<style>\n' + data.decode("utf-8") + '\n</style>'


STYLE_BLOCK = load_style()
