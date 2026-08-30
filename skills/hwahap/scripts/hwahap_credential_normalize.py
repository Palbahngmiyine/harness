"""Normalize credential text while preserving raw source offsets."""

import re
import unicodedata

from hwahap_credential_patterns import DROP_RANGES
from hwahap_credential_types import NormalizedView


def _ignored(char: str) -> bool:
    code = ord(char)
    category = unicodedata.category(char)
    return (char in "\u2028\u2029"
            or category[0] == "C" and char not in "\r\n\t"
            or any(start <= code <= end for start, end in DROP_RANGES))


def _views(value: str) -> tuple[NormalizedView, NormalizedView]:
    raw = value.replace("\r\n", "\n").replace("\r", "\n\t")
    raw = raw.replace("\f", " ").replace("\v", " ").replace("\u00a0", " ")
    raw = re.sub(r"[ \t]*\\\n[ \t]*", " ", raw)
    dropped, spaced, drop_origins, space_origins = [], [], [], []
    for index, char in enumerate(raw):
        if _ignored(char):
            spaced.append(" ")
            space_origins.append(index)
            continue
        dropped.append(char)
        drop_origins.append(index)
        spaced.append(char)
        space_origins.append(index)
    return (
        NormalizedView(raw, "".join(dropped), tuple(drop_origins)),
        NormalizedView(raw, "".join(spaced), tuple(space_origins)),
    )


def view(value: str) -> NormalizedView:
    return _views(value)[0]


def normalized_text(value: str) -> str:
    return view(value).text


def is_redacted(match: re.Match[str]) -> bool:
    value = match.groupdict().get("value", "").strip().strip("\"'")
    if re.match(r"(?i)^(?:bearer|basic|digest)\s+", value):
        value = value.split(None, 1)[1]
    marker = re.match(r"\[redacted[^\]]*\]", value)
    return bool(marker and not value[marker.end():].strip())
