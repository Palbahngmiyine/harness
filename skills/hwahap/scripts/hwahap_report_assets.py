"""Load pinned static report assets."""

import hashlib
from pathlib import Path

STYLE_SHA256 = "db41d318e514e396304c375907e3208be64eb637924ea5b73ae4f2fe880bf17f"
META_STATIC = (
    '<meta charset="utf-8">',
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    '<meta name="color-scheme" content="light dark">',
    '<meta name="material-design-system" content="Material Design 3">',
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
