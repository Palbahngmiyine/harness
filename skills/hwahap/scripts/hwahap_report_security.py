"""Credential-backed report text redaction."""

import re
from typing import Any

from hwahap_report_types import ABS_PATH, HwahapReportError

_module = None


def _credentials():
    if _module is None:
        raise HwahapReportError("report credential dependency unavailable")
    return _module


def credential_bearing_text(value: object) -> bool:
    return isinstance(value, str) and _credentials().credential_bearing_text(value)


def text(value: Any, workspace: str = "") -> str:
    if not isinstance(value, str):
        return str(value) if value is not None else ""
    value = _credentials().redact(value)
    if workspace.rstrip("/"):
        value = re.sub(re.escape(workspace.rstrip("/")) + r"(?=/|$)",
                       "$WORKSPACE", value)
    return ABS_PATH.sub("[external reference]", value).strip()
