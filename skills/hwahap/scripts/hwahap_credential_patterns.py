"""Credential patterns shared by state and report validation."""

import re

DROP_RANGES = (
    (0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C),
    (0x115F, 0x1160), (0x17B4, 0x17B5), (0x180B, 0x180F),
    (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x206F),
    (0x3164, 0x3164), (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0), (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A),
    (0xE0001, 0xE0001), (0xE0020, 0xE007F), (0xE0100, 0xE01EF),
)
ASSIGNMENT_CREDENTIAL = re.compile(
    r"(?ix)(?<![a-z0-9_-])(?:(?:[a-z0-9]+(?:[_ -]+[a-z0-9]+)*[_ -]+)?"
    r"(?:private[_ -]+key|secret[_ -]+key|api[_ -]+key|access[_ -]+key|"
    r"token|secret|password))(?=[\s]*(?::=|=|:))[\s]*(?::=|=|:)[\s]*"
    r"(?P<value>[^\r\n]+(?:\r?\n[ \t]+[^\r\n]*)*)")
AUTH_HEADER_CREDENTIAL = re.compile(
    r"(?ix)(?<![a-z0-9_-])(?:authorization|proxy-authorization)\s*"
    r"(?::=|=|:)\s*(?P<value>(?:(?:bearer|basic|digest)\s+)?"
    r"[^\r\n]+(?:\r?\n[ \t]+[^\r\n]*)*)")
HEADER_CREDENTIAL = re.compile(
    r"(?ix)(?<![a-z0-9_-])(?:bearer|cookie|set-cookie|password|secret|"
    r"x[ _-]?api[ _-]?key|api[ _-]?key|private[ _-]?key)\s*"
    r"(?::=|=|:)\s*(?P<value>[^\r\n]+(?:\r?\n[ \t]+[^\r\n]*)*)")
BEARER_CREDENTIAL = re.compile(
    r"(?i)(?<![a-z0-9_-])bearer\s+(?P<value>[^\s,;<>]+)")
FLAG_CREDENTIAL = re.compile(
    r"(?ix)(?<![a-z0-9_-])--(?:token|session-token|password|secret|"
    r"api[_-]?key|private[_-]?key)(?:=|\s+)(?P<value>\"[^\"]*\"|"
    r"'[^']*'|[^\s,;<>]+)")
CURL_CREDENTIAL = re.compile(
    r"(?ix)(?<![a-z0-9_-])curl(?![a-z0-9_-])[^\r\n;|&<>`]*?\s"
    r"(?:(?:-u|-U)(?:=|\s*)|(?:--user|--proxy-user|--oauth2-bearer)"
    r"(?:=|\s+))(?P<value>\"[^\"]*\"|'[^']*'|[^\s,;<>]+)")
CREDENTIAL_URL = re.compile(r"(?i)https?://[^/\s:@]+:[^/\s@]+@[^\s<>\"']*")
PEM = re.compile(r"-----BEGIN [^-]+-----.*?(?:-----END [^-]+-----|$)", re.DOTALL)
PROVIDER_TOKEN = re.compile(
    r"(?x)(?<![A-Za-z0-9_-])(?P<value>(?:gh[pousr]_[A-Za-z0-9]{36,255}|"
    r"github_pat_[A-Za-z0-9_]{20,255}|sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{20,}|npm_[A-Za-z0-9]{20,}|"
    r"(?:sk|rk)_live_[A-Za-z0-9]{16,}|AIza[0-9A-Za-z_-]{35}|"
    r"(?:AKIA|ASIA)[A-Z0-9]{16}))(?![A-Za-z0-9_-])")
HIGH_ENTROPY = re.compile(
    r"(?<![A-Za-z0-9_+/=-])(?P<value>[A-Za-z0-9_+/-]{32,}={0,2})"
    r"(?![A-Za-z0-9_+/=-])")
