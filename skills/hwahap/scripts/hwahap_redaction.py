"""Detect and redact sensitive data before Hwahap persists or reports it."""
from dataclasses import dataclass
import math
import re
import unicodedata

_DICP16 = ((0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C),
           (0x115F, 0x1160), (0x17B4, 0x17B5), (0x180B, 0x180F),
           (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x206F),
           (0x3164, 0x3164), (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF),
           (0xFFA0, 0xFFA0), (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A),
           (0xE0001, 0xE0001), (0xE0020, 0xE007F), (0xE0100, 0xE01EF))

ASSIGNMENT_SECRET_PATTERN = re.compile(
    r"(?ix)(?<![a-z0-9_-])(?:(?:[a-z0-9]+(?:[_ -]+[a-z0-9]+)*[_ -]+)?"
    r"(?:private[_ -]+key|secret[_ -]+key|api[_ -]+key|access[_ -]+key|token|secret|password))"
    r"(?=[\s]*(?>:=|=|:))[\s]*(?>:=|=|:)[\s]*"
    r"(?P<value>[^\r\n]+(?:\r?\n[ \t]+[^\r\n]*)*)")
AUTH_HEADER_SECRET_PATTERN = re.compile(
    r"(?ix)(?<![a-z0-9_-])(?:authorization|proxy-authorization)\s*(?>:=|=|:)\s*"
    r"(?P<value>(?:(?:bearer|basic|digest)\s+)?[^\r\n]+(?:\r?\n[ \t]+[^\r\n]*)*)")
HEADER_SECRET_PATTERN = re.compile(
    r"(?ix)(?<![a-z0-9_-])(?:bearer|cookie|set-cookie|password|secret|"
    r"x[ _-]?api[ _-]?key|api[ _-]?key|private[ _-]?key)\s*(?>:=|=|:)\s*"
    r"(?P<value>[^\r\n]+(?:\r?\n[ \t]+[^\r\n]*)*)")
BEARER_TOKEN_PATTERN = re.compile(r"(?i)(?<![a-z0-9_-])bearer\s+(?P<value>[^\s,;<>]+)")
SECRET_FLAG_PATTERN = re.compile(
    r"(?ix)(?<![a-z0-9_-])--(?:token|session-token|password|secret|api[_-]?key|private[_-]?key)"
    r"(?:=|\s+)(?P<value>\"[^\"]*\"|'[^']*'|[^\s,;<>]+)")
CURL_AUTH_PATTERN = re.compile(
    r"(?ix)(?<![a-z0-9_-])curl(?![a-z0-9_-])[^\r\n;|&<>`]*?\s(?:"
    r"(?:-u|-U)(?:=|\s*)|(?:--user|--proxy-user|--oauth2-bearer)(?:=|\s+))"
    r"(?P<value>\"[^\"]*\"|'[^']*'|[^\s,;<>]+)")
CREDENTIAL_URL_PATTERN = re.compile(r"(?i)https?://[^/\s:@]+:[^/\s@]+@[^\s<>\"']*")
PEM_PRIVATE_KEY_PATTERN = re.compile(r"-----BEGIN [^-]+-----.*?(?:-----END [^-]+-----|$)", re.DOTALL)
PROVIDER_TOKEN_PATTERN = re.compile(
    r"(?x)(?<![A-Za-z0-9_-])(?P<value>(?:"
    r"gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{20,255}|"
    r"sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|"
    r"npm_[A-Za-z0-9]{20,}|(?:sk|rk)_live_[A-Za-z0-9]{16,}|"
    r"AIza[0-9A-Za-z_-]{35}|(?:AKIA|ASIA)[A-Z0-9]{16}"
    r"))(?![A-Za-z0-9_-])")
HIGH_ENTROPY_SECRET_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_+/=-])(?P<value>[A-Za-z0-9_+/-]{32,}={0,2})(?![A-Za-z0-9_+/=-])")

@dataclass(frozen=True)
class NormalizedView:
    raw: str
    text: str
    origins: tuple[int, ...]

@dataclass(frozen=True)
class SensitiveDataFinding:
    kind: str
    start: int
    end: int
    value_start: int = 0
    value_end: int = 0
    scheme: str = ""
    normalized_start: int = 0
    normalized_end: int = 0
    normalized_value_start: int = 0
    normalized_value_end: int = 0


def _views(value: str) -> tuple[NormalizedView, NormalizedView]:
    raw = value.replace("\r\n", "\n").replace("\r", "\n\t")
    raw = raw.replace("\f", " ").replace("\v", " ").replace("\u00a0", " ")
    raw = re.sub(r"[ \t]*\\(?:\n)[ \t]*", " ", raw)
    dropped, spaced, dropped_origins, spaced_origins = [], [], [], []
    for index, char in enumerate(raw):
        if _ignored(char):
            spaced.append(" ")
            spaced_origins.append(index)
        else:
            dropped.append(char)
            dropped_origins.append(index)
            spaced.append(char)
            spaced_origins.append(index)
    return (NormalizedView(raw, "".join(dropped), tuple(dropped_origins)),
            NormalizedView(raw, "".join(spaced), tuple(spaced_origins)))

def _ignored(char: str) -> bool:
    code = ord(char)
    # Unicode Zl/Zp separators are explicit key/operator obfuscators here.
    if char in "\u2028\u2029":
        return True
    if (unicodedata.category(char) in {"Cc", "Cf", "Co"}
            or 0xFDD0 <= code <= 0xFDEF or code & 0xFFFF in (0xFFFE, 0xFFFF)):
        return char not in "\r\n\t"
    return any(lo <= code <= hi for lo, hi in _DICP16)

def view(value: str) -> NormalizedView:
    return _views(value)[0]

def normalized_text(value: str) -> str:
    return view(value).text

def is_redacted(match: re.Match[str]) -> bool:
    value = match.groupdict().get("value", "").strip().strip("\"'")
    if re.match(r"(?i)^(?:bearer|basic|digest)\s+", value):
        value = value.split(None, 1)[1]
    marker = re.match(r"\[redacted[^\]]*\]", value)
    return bool(marker and value[marker.end():].strip() == "")

def _finding(viewed: NormalizedView, match: re.Match[str], kind: str) -> SensitiveDataFinding:
    start, end = match.span()
    value_start, value_end = match.span("value") if "value" in match.groupdict() else (start, end)
    scheme = ""
    if kind == "auth":
        scheme_match = re.match(r"(?i)(bearer|basic|digest)\s+", match.group("value").strip())
        scheme = scheme_match.group(1).title() if scheme_match else ""
    def raw_span(left: int, right: int) -> tuple[int, int]:
        if right <= left or not viewed.origins:
            return (len(viewed.raw), len(viewed.raw))
        return (viewed.origins[left], viewed.origins[right - 1] + 1)
    raw_start, raw_end = raw_span(start, end)
    raw_value_start, raw_value_end = raw_span(value_start, value_end)
    return SensitiveDataFinding(kind, raw_start, raw_end, raw_value_start, raw_value_end, scheme,
                             start, end, value_start, value_end)

def _looks_like_high_entropy_secret(value: str) -> bool:
    if value.count("/") > 1 or re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", value):
        return False
    classes = sum(bool(re.search(pattern, value)) for pattern in
                  (r"[a-z]", r"[A-Z]", r"[0-9]", r"[_+/=-]"))
    if classes < 3:
        return False
    counts = {char: value.count(char) for char in set(value)}
    entropy = -sum((count / len(value)) * math.log2(count / len(value))
                   for count in counts.values())
    return entropy >= 4.0

def _findings_for_view(viewed: NormalizedView) -> list[SensitiveDataFinding]:
    found = []
    safe_headers = []
    for kind, pattern in (("auth", AUTH_HEADER_SECRET_PATTERN), ("header", HEADER_SECRET_PATTERN)):
        for match in pattern.finditer(viewed.text):
            item = _finding(viewed, match, kind)
            if not is_redacted(match):
                found.append(item)
            else:
                safe_headers.append(match.span())
    scrubbed = list(viewed.text)
    for start, end in safe_headers:
        scrubbed[start:end] = [" "] * (end - start)
    generic = (("assignment", ASSIGNMENT_SECRET_PATTERN), ("bearer", BEARER_TOKEN_PATTERN),
               ("flag", SECRET_FLAG_PATTERN), ("curl", CURL_AUTH_PATTERN))
    for kind, pattern in generic:
        for match in pattern.finditer("".join(scrubbed)):
            if not is_redacted(match):
                found.append(_finding(viewed, match, kind))
    for kind, pattern in (("url", CREDENTIAL_URL_PATTERN), ("pem", PEM_PRIVATE_KEY_PATTERN)):
        for match in pattern.finditer(viewed.text):
            found.append(_finding(viewed, match, kind))
    for match in PROVIDER_TOKEN_PATTERN.finditer(viewed.text):
        found.append(_finding(viewed, match, "provider-token"))
    for match in HIGH_ENTROPY_SECRET_PATTERN.finditer(viewed.text):
        if _looks_like_high_entropy_secret(match.group("value")):
            found.append(_finding(viewed, match, "high-entropy-secret"))
    return found


def findings(value: str) -> tuple[SensitiveDataFinding, ...]:
    unique = {}
    for viewed in _views(value):
        for item in _findings_for_view(viewed):
            key = (item.kind, item.start, item.end, item.value_start, item.value_end, item.scheme)
            unique.setdefault(key, item)
    return tuple(sorted(unique.values(), key=lambda item: (
        item.start, item.end, item.kind, item.value_start, item.value_end, item.scheme)))

def contains_sensitive_data(value: object) -> bool:
    return isinstance(value, str) and bool(findings(value))

def redact(value: str) -> str:
    viewed = view(value)
    replacements = []
    for item in findings(value):
        start, end = item.value_start, item.value_end
        replacement = {"url": "[redacted credential URL]", "pem": "[redacted private key]",
                       "provider-token": "[redacted provider token]",
                       "high-entropy-secret": "[redacted possible secret]"}.get(item.kind)
        if replacement is None:
            replacement = f"{item.scheme} [redacted]" if item.scheme else "[redacted]"
        replacements.append((start, end, replacement))
    merged = []
    for start, end, replacement in sorted(replacements, key=lambda item: (item[0], -item[1])):
        if merged and start < merged[-1][1]:
            if end > merged[-1][1]:
                merged[-1] = (merged[-1][0], end, replacement)
        else:
            merged.append((start, end, replacement))
    result = viewed.raw
    for start, end, replacement in reversed(merged):
        result = result[:start] + replacement + result[end:]
    return result
