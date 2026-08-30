"""Find and redact credentials with stable raw offsets."""

import re

from hwahap_credential_normalize import _views, is_redacted, view
from hwahap_credential_patterns import (
    ASSIGNMENT_CREDENTIAL, AUTH_HEADER_CREDENTIAL, BEARER_CREDENTIAL,
    CREDENTIAL_URL, CURL_CREDENTIAL, FLAG_CREDENTIAL, HEADER_CREDENTIAL, PEM,
)
from hwahap_credential_types import CredentialFinding, NormalizedView


def _finding(value: NormalizedView, match: re.Match[str], kind: str) -> CredentialFinding:
    start, end = match.span()
    value_start, value_end = (
        match.span("value") if "value" in match.groupdict() else (start, end))
    scheme = ""
    if kind == "auth":
        prefix = re.match(r"(?i)(bearer|basic|digest)\s+",
                          match.group("value").strip())
        scheme = prefix.group(1).title() if prefix else ""

    def raw_span(first: int, last: int) -> tuple[int, int]:
        if last > first and value.origins:
            return value.origins[first], value.origins[last - 1] + 1
        return len(value.raw), len(value.raw)

    raw_start, raw_end = raw_span(start, end)
    raw_value_start, raw_value_end = raw_span(value_start, value_end)
    return CredentialFinding(kind, raw_start, raw_end, raw_value_start,
        raw_value_end, scheme, start, end, value_start, value_end)


def _findings(value: NormalizedView) -> list[CredentialFinding]:
    found, safe = [], []
    for kind, pattern in (("auth", AUTH_HEADER_CREDENTIAL),
                          ("header", HEADER_CREDENTIAL)):
        for match in pattern.finditer(value.text):
            if is_redacted(match):
                safe.append(match.span())
            else:
                found.append(_finding(value, match, kind))
    visible = list(value.text)
    for start, end in safe:
        visible[start:end] = [" "] * (end - start)
    text = "".join(visible)
    patterns = (("assignment", ASSIGNMENT_CREDENTIAL),
                ("bearer", BEARER_CREDENTIAL), ("flag", FLAG_CREDENTIAL),
                ("curl", CURL_CREDENTIAL))
    for kind, pattern in patterns:
        found.extend(_finding(value, match, kind)
                     for match in pattern.finditer(text) if not is_redacted(match))
    for kind, pattern in (("url", CREDENTIAL_URL), ("pem", PEM)):
        found.extend(_finding(value, match, kind)
                     for match in pattern.finditer(value.text))
    return found


def findings(value: str) -> tuple[CredentialFinding, ...]:
    unique = {}
    for normalized in _views(value):
        for item in _findings(normalized):
            key = (item.kind, item.start, item.end, item.value_start,
                   item.value_end, item.scheme)
            unique.setdefault(key, item)
    return tuple(sorted(unique.values(), key=lambda item: (
        item.start, item.end, item.kind, item.value_start,
        item.value_end, item.scheme)))


def credential_bearing_text(value: object) -> bool:
    return isinstance(value, str) and bool(findings(value))


def redact(value: str) -> str:
    replacements = []
    for item in findings(value):
        marker = {"url": "[redacted credential URL]",
                  "pem": "[redacted private key]"}.get(item.kind, "[redacted]")
        if item.scheme:
            marker = f"{item.scheme} [redacted]"
        replacements.append((item.value_start, item.value_end, marker))
    merged = []
    for start, end, marker in sorted(replacements):
        if merged and start < merged[-1][1]:
            if end > merged[-1][1]:
                merged[-1] = (merged[-1][0], end, marker)
        else:
            merged.append((start, end, marker))
    result = view(value).raw
    for start, end, marker in reversed(merged):
        result = result[:start] + marker + result[end:]
    return result
