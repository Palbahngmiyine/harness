"""Verified importer for the report runtime graph."""

import hashlib
import hmac
import json
import os
import stat
import sys
import types
from pathlib import Path


def _read(directory: Path, name: str, digest: str) -> bytes:
    dfd = fd = None
    try:
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
        dfd = os.open(directory, flags | os.O_DIRECTORY)
        dir_before = os.fstat(dfd)
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
        directory_same = (dir_before.st_dev, dir_before.st_ino) == (
            os.fstat(dfd).st_dev, os.fstat(dfd).st_ino)
        if not safe or not same or not directory_same or len(data) != before.st_size:
            raise ValueError
        if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), digest):
            raise ValueError
        return data
    finally:
        for descriptor in (fd, dfd):
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass


def load_graph(directory: Path, manifest_bytes: bytes) -> dict[str, object]:
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, list):
        raise ImportError("report dependency unavailable")
    loaded = {}
    try:
        for item in manifest:
            name, filename, digest = item["name"], item["file"], item["sha256"]
            if filename != name + ".py" or not digest or name in loaded:
                raise ValueError
            source = _read(directory, filename, digest)
            module = types.ModuleType(name)
            module.__file__ = str(directory / filename)
            sys.modules[name] = module
            exec(compile(source, f"<verified:{name}>", "exec"), module.__dict__)
            loaded[name] = module
        return loaded
    except Exception:
        for name in loaded:
            sys.modules.pop(name, None)
        raise ImportError("report dependency unavailable") from None
