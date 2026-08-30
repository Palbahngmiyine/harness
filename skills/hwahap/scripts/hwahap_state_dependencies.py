"""Verified external dependency handles."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())

_dependency_modules = None
_report_module = None


def _ensure_dependencies() -> None:
    if _dependency_modules is None:
        raise HwahapError("HW_STATE_INVALID", "state dependency unavailable")
