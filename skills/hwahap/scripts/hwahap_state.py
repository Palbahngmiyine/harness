#!/usr/bin/env python3
"""Verified facade for Hwahap orchestration state."""
from __future__ import annotations

import hashlib
import hmac
import importlib.abc
import importlib.util
import os
import stat
import sys
from pathlib import Path

_BOOT_PIN = "1e14dad517422e63a676f09cb973e6aef3aae7ae70a60c224cead8370ee3e5b4"
_MANIFEST_PIN = "47e65bd986a9a3b9d8f759fa2494484d01edacdc639c50b343797082c2cdee06"


class HwahapError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _read(name: str, digest: str) -> bytes:
    directory, dfd, fd = Path(__file__).parent, None, None
    try:
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
        dfd = os.open(directory, flags | os.O_DIRECTORY)
        directory_before = os.fstat(dfd)
        fd = os.open(name, flags, dir_fd=dfd)
        before = os.fstat(fd)
        safe = (stat.S_ISREG(before.st_mode) and before.st_uid in (0, os.geteuid())
                and before.st_mode & 0o444 and not before.st_mode & 0o022
                and before.st_size <= 2 * 1024 * 1024)
        data = os.read(fd, before.st_size + 1)
        after = os.fstat(fd)
        identity = (before.st_dev, before.st_ino, before.st_size,
                    before.st_mtime_ns, before.st_ctime_ns)
        same = identity == (after.st_dev, after.st_ino, after.st_size,
                            after.st_mtime_ns, after.st_ctime_ns)
        directory_after = os.fstat(dfd)
        unchanged = (directory_before.st_dev, directory_before.st_ino) == (
            directory_after.st_dev, directory_after.st_ino)
        if (not safe or not same or not unchanged or len(data) != before.st_size
                or not hmac.compare_digest(hashlib.sha256(data).hexdigest(), digest)):
            raise ValueError
        return data
    finally:
        for descriptor in (fd, dfd):
            if descriptor is not None:
                os.close(descriptor)


class _Loader(importlib.abc.SourceLoader):
    def __init__(self, name: str, filename: str, digest: str) -> None:
        self.name, self.filename, self.digest = name, filename, digest
    def get_filename(self, fullname: str) -> str:
        return str(Path(__file__).with_name(self.filename))
    def get_data(self, path: str) -> bytes:
        if Path(path) != Path(self.get_filename(self.name)):
            raise OSError
        return _read(self.filename, self.digest)
    def set_data(self, path: str, data: bytes) -> None:
        return None


class _Finder(importlib.abc.MetaPathFinder):
    def __init__(self, entries: dict) -> None:
        self.entries = entries
    def find_spec(self, fullname: str, path=None, target=None):
        if fullname not in self.entries:
            return None
        filename, digest = self.entries[fullname]
        return importlib.util.spec_from_loader(
            fullname, _Loader(fullname, filename, digest))


def _load_boot():
    finder = _Finder({"hwahap_state_boot": ("hwahap_state_boot.py", _BOOT_PIN)})
    try:
        sys.meta_path.insert(0, finder)
        import hwahap_state_boot as boot
        return boot
    finally:
        sys.meta_path.remove(finder)
        sys.modules.pop("hwahap_state_boot", None)


_boot = _load_boot()
_boot.install(globals(), sys.modules.get(__name__), HwahapError,
              _Finder, _read, _MANIFEST_PIN)
if __name__ == "__main__":
    raise SystemExit(_boot.run())
