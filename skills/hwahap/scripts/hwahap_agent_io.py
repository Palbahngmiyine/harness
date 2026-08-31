"""Descriptor helpers shared by the Hwahap profile installer."""

import hashlib
import hmac
import os
import stat

from hwahap_agent_contract import InstallError, REQUIRED_PROFILE_NAMES, is_hwahap_profile_name

DF = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
PF = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)


def file_id(info):
    return info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode)


def open_dir(parent, name, create=False):
    try:
        return os.open(name, DF, **({} if parent is None else {"dir_fd": parent}))
    except FileNotFoundError:
        if not create or parent is None:
            raise InstallError("HW_AGENT_PATH_INVALID", "required directory is unavailable")
        try:
            os.mkdir(name, 0o755, dir_fd=parent)
        except FileExistsError:
            pass
        except OSError as exc:
            raise InstallError("HW_AGENT_INSTALL_FAILED", "cannot create required directory") from exc
        return open_dir(parent, name)
    except OSError as exc:
        raise InstallError("HW_AGENT_PATH_INVALID", "required directory is invalid") from exc


def read_profile(fd, name):
    handle = -1
    try:
        handle = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=fd)
        if not stat.S_ISREG(os.fstat(handle).st_mode):
            raise InstallError("HW_AGENT_PATH_INVALID", "target must be a regular file")
        return os.read(handle, 1 << 20)
    except InstallError:
        raise
    except OSError as exc:
        raise InstallError("HW_AGENT_INSTALL_FAILED", "cannot inspect existing profile") from exc
    finally:
        if handle >= 0:
            try: os.close(handle)
            except OSError: pass


def reject_extras(fd):
    try: names = os.listdir(fd)
    except OSError as exc: raise InstallError("HW_AGENT_INSTALL_FAILED", "cannot inspect profile directory") from exc
    if any(is_hwahap_profile_name(n) and n not in REQUIRED_PROFILE_NAMES for n in names):
        raise InstallError("HW_AGENT_CONFLICT", "unexpected Hwahap profile")


def assert_bound(workspace, codex, ci, ai):
    try:
        codex_info = os.stat(".codex", dir_fd=workspace, follow_symlinks=False)
        agents_info = os.stat("agents", dir_fd=codex, follow_symlinks=False)
    except OSError as exc: raise OSError("directory binding changed") from exc
    if any(not stat.S_ISDIR(x.st_mode) or file_id(x) != y for x, y in ((codex_info, ci), (agents_info, ai))):
        raise OSError("directory binding changed")


def cleanup(fd, created):
    complete = True
    for name, guard, expected in reversed(created):
        candidate = -1
        try:
            if guard is None: complete = False; continue
            candidate = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=fd)
            info, guarded = os.fstat(candidate), os.fstat(guard)
            digest = hashlib.sha256(os.read(candidate, 1 << 20)).hexdigest()
            current = os.stat(name, dir_fd=fd, follow_symlinks=False)
            digest_matches = expected is None or hmac.compare_digest(digest, expected)
            if (not stat.S_ISREG(info.st_mode) or file_id(info) != file_id(guarded)
                    or not digest_matches or file_id(current) != file_id(info)):
                complete = False; continue
            os.unlink(name, dir_fd=fd)
        except FileNotFoundError:
            pass
        except Exception:
            complete = False
        finally:
            if candidate >= 0:
                try: os.close(candidate)
                except OSError: complete = False
    return complete
