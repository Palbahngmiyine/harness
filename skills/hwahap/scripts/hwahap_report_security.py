"""Pinned credential engine and report text redaction."""

import hashlib
import hmac
import os
import re
import stat
import sys
import types
from pathlib import Path
from typing import Any

from hwahap_report_types import ABS_PATH, HwahapReportError

PIN = "8e439402951854de3a60ba24d16566d7146be2eeb4572d515ef2d35ce488b1ab"
_module = None


def _sealed_module(filename: str, digest: str, exports: tuple[str, ...], error: str):
    directory = Path(__file__).parent
    dfd = fd = None
    try:
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
        dfd = os.open(directory, flags | os.O_DIRECTORY)
        before_dir = os.fstat(dfd)
        fd = os.open(filename, flags, dir_fd=dfd)
        before = os.fstat(fd)
        safe = (stat.S_ISREG(before.st_mode) and before.st_uid in (0, os.geteuid())
                and before.st_mode & 0o444 and not before.st_mode & 0o022
                and before.st_size <= 2 * 1024 * 1024)
        data = os.read(fd, before.st_size + 1)
        after = os.fstat(fd)
        same = (before.st_dev, before.st_ino, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns) == (
                    after.st_dev, after.st_ino, after.st_size,
                    after.st_mtime_ns, after.st_ctime_ns)
        directory_same = (before_dir.st_dev, before_dir.st_ino) == (
            os.fstat(dfd).st_dev, os.fstat(dfd).st_ino)
        if not safe or not same or not directory_same or len(data) != before.st_size:
            raise ValueError
        if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), digest):
            raise ValueError
        module = types.ModuleType("_hwahap_report_credentials")
        module.__file__ = str(directory / filename)
        sys.modules[module.__name__] = module
        exec(compile(data, "<hwahap-credentials>", "exec"), module.__dict__)
        if any(not hasattr(module, name) for name in exports):
            raise ValueError
        return module
    except Exception:
        raise ImportError(error) from None
    finally:
        sys.modules.pop("_hwahap_report_credentials", None)
        for descriptor in (fd, dfd):
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass


def _credentials():
    global _module
    if _module is None:
        try:
            _module = _sealed_module("hwahap_credentials.py", PIN,
                ("credential_bearing_text", "redact"),
                "credential dependency unavailable")
        except ImportError:
            raise HwahapReportError("report credential dependency unavailable") from None
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
