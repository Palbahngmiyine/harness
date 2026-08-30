#!/usr/bin/env python3
"""Install Hwahap project agents without overwriting existing files."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import shutil
import stat
import sys
import tomllib
from pathlib import Path


PROFILE_DIR = Path(__file__).resolve().parents[1] / "assets" / "agents"
REQUIRED_FIELDS = ("name", "description", "developer_instructions")
PROFILE_CONTRACT = {
    "hwahap-luna-implementer.toml": {
        "name": "hwahap-luna-implementer", "model": "gpt-5.6-luna",
        "model_reasoning_effort": "high", "sandbox_mode": "workspace-write",
        "service_tier": None, "fast_mode": None,
    },
    "hwahap-luna-verifier.toml": {
        "name": "hwahap-luna-verifier", "model": "gpt-5.6-luna",
        "model_reasoning_effort": "xhigh", "sandbox_mode": "read-only",
        "service_tier": None, "fast_mode": None,
    },
    "hwahap-sol-final-reviewer.toml": {
        "name": "hwahap-sol-final-reviewer", "model": "gpt-5.6-sol",
        "model_reasoning_effort": None, "sandbox_mode": "read-only",
        "service_tier": None, "fast_mode": None,
    },
    "hwahap-sol-planner.toml": {
        "name": "hwahap-sol-planner", "model": "gpt-5.6-sol",
        "model_reasoning_effort": "xhigh", "sandbox_mode": "read-only",
        "service_tier": None, "fast_mode": None,
    },
    "hwahap-sol-orchestrator.toml": {
        "name": "hwahap-sol-orchestrator", "model": "gpt-5.6-sol",
        "model_reasoning_effort": "xhigh", "sandbox_mode": "workspace-write",
        "service_tier": "fast", "fast_mode": True,
    },
    "hwahap-terra-scope-reviewer.toml": {
        "name": "hwahap-terra-scope-reviewer", "model": "gpt-5.6-terra",
        "model_reasoning_effort": "xhigh", "sandbox_mode": "read-only",
        "service_tier": None, "fast_mode": None,
    },
}
REQUIRED_PROFILE_NAMES = frozenset(PROFILE_CONTRACT)
PROFILE_SHA256 = {
    "hwahap-luna-implementer.toml": "f1781d1f33f923ce4f75b485444e3bd3c8779fdd1304c11b515777eb850586ae",
    "hwahap-luna-verifier.toml": "3f78b091ceccd232bd2206587a74259a139ea962d1736189d3ffd1d8b2a45df5",
    "hwahap-sol-final-reviewer.toml": "45b7f0d6961ccec665acc0c738f9506b6e2958b58ff5faff6248e91c6eb79f15",
    "hwahap-sol-orchestrator.toml": "239d05fc08b48000309a899f36ddf7a3ae218ff04a00610fa8a050df2515f62b",
    "hwahap-terra-scope-reviewer.toml": "381b8ebccc833408bce908e47f686fd42c22f51982865d3d27804dc204d8fed0",
}
PUBLIC_ERROR_MESSAGES = {
    "HW_AGENT_ARGUMENT_INVALID": "invalid installer arguments",
    "HW_AGENT_SOURCE_INVALID": "Hwahap source profiles are invalid",
    "HW_AGENT_PATH_INVALID": "installer path is invalid",
    "HW_AGENT_CONFLICT": "profile installation conflict",
    "HW_AGENT_CONFIG_INVALID": "installed agent configuration is invalid",
    "HW_AGENT_INSTALL_FAILED": "profile installation failed",
}


def is_hwahap_profile_name(name: str) -> bool:
    folded = name.casefold()
    return folded.startswith("hwahap-") and folded.endswith(".toml")


class InstallError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InstallError("HW_AGENT_ARGUMENT_INVALID", "invalid installer arguments")


def _profile_metadata_matches(value: dict, expected: dict) -> bool:
    for key in ("name", "model", "model_reasoning_effort", "sandbox_mode", "service_tier"):
        if expected[key] is None:
            if key in value:
                return False
        elif value.get(key) != expected[key]:
            return False
    features = value.get("features")
    if expected["fast_mode"] is None:
        return not isinstance(features, dict) or "fast_mode" not in features
    return isinstance(features, dict) and features.get("fast_mode") is expected["fast_mode"]


def source_profiles(profile_dir: Path | None = None) -> list[tuple[Path, bytes]]:
    directory = profile_dir or PROFILE_DIR
    try:
        if directory.is_symlink() or not directory.is_dir():
            raise InstallError("HW_AGENT_SOURCE_INVALID", "invalid profile directory")
        profiles = sorted(directory.iterdir())
    except InstallError:
        raise
    except (OSError, UnicodeError) as exc:
        raise InstallError("HW_AGENT_SOURCE_INVALID", "cannot inspect Hwahap profile directory") from exc
    hwahap_names = {path.name for path in profiles if is_hwahap_profile_name(path.name)}
    if hwahap_names != REQUIRED_PROFILE_NAMES:
        raise InstallError("HW_AGENT_SOURCE_INVALID", "source profiles must contain exactly the required Hwahap profiles")
    parsed: list[tuple[Path, bytes]] = []
    for name in sorted(REQUIRED_PROFILE_NAMES):
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise InstallError("HW_AGENT_SOURCE_INVALID", "invalid Hwahap profile")
        try:
            raw = path.read_bytes()
            value = tomllib.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            raise InstallError("HW_AGENT_SOURCE_INVALID", "cannot parse Hwahap profile") from exc
        if not isinstance(value, dict) or any(not isinstance(value.get(field), str) or not value[field].strip() for field in REQUIRED_FIELDS):
            raise InstallError("HW_AGENT_SOURCE_INVALID", "Hwahap profile required fields are invalid")
        expected = PROFILE_CONTRACT[path.name]
        digest = hashlib.sha256(raw).hexdigest()
        if (not hmac.compare_digest(digest, PROFILE_SHA256[path.name])
                or not _profile_metadata_matches(value, expected) or value["name"] != path.stem):
            raise InstallError("HW_AGENT_SOURCE_INVALID", "Hwahap profile metadata is invalid")
        parsed.append((path, raw))
    return parsed


def _file_identity(info: os.stat_result) -> tuple[int, int, int]:
    return (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode))


def _digest_open_file(fd: int) -> str:
    digest = hashlib.sha256()
    while chunk := os.read(fd, 64 * 1024):
        digest.update(chunk)
    return digest.hexdigest()


def cleanup_created(agents_fd: int, targets: list[tuple[str, int | None, str]]) -> bool:
    complete = True
    for name, guard_fd, expected_digest in reversed(targets):
        candidate_fd = -1
        try:
            if guard_fd is None:
                complete = False
                continue
            candidate_fd = os.open(
                name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=agents_fd)
            guarded = os.fstat(guard_fd)
            candidate = os.fstat(candidate_fd)
            if (not stat.S_ISREG(candidate.st_mode)
                    or _file_identity(candidate) != _file_identity(guarded)
                    or not hmac.compare_digest(_digest_open_file(candidate_fd), expected_digest)):
                complete = False
                continue
            current = os.stat(name, dir_fd=agents_fd, follow_symlinks=False)
            if _file_identity(current) != _file_identity(candidate):
                complete = False
                continue
            os.unlink(name, dir_fd=agents_fd)
        except FileNotFoundError:
            pass
        except Exception:
            complete = False
        finally:
            if candidate_fd >= 0:
                try: os.close(candidate_fd)
                except Exception: complete = False
    return complete


_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_PROFILE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)


def _open_directory(parent_fd: int | None, name: str | Path, create: bool = False) -> int:
    kwargs = {} if parent_fd is None else {"dir_fd": parent_fd}
    try:
        return os.open(name, _DIRECTORY_FLAGS, **kwargs)
    except FileNotFoundError:
        if not create or parent_fd is None:
            raise InstallError("HW_AGENT_PATH_INVALID", "required directory is unavailable")
        try:
            os.mkdir(name, 0o755, dir_fd=parent_fd)
        except FileExistsError:
            pass
        except OSError as exc:
            raise InstallError("HW_AGENT_INSTALL_FAILED", "cannot create required directory") from exc
        return _open_directory(parent_fd, name)
    except OSError as exc:
        raise InstallError("HW_AGENT_PATH_INVALID", "required directory is invalid") from exc


def _read_profile_at(agents_fd: int, name: str) -> bytes:
    fd = -1
    try:
        fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=agents_fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise InstallError("HW_AGENT_PATH_INVALID", "target must be a regular file")
        return os.read(fd, 1 << 20)
    except InstallError:
        raise
    except OSError as exc:
        raise InstallError("HW_AGENT_INSTALL_FAILED", "cannot inspect existing profile") from exc
    finally:
        if fd >= 0:
            try: os.close(fd)
            except Exception: pass


def _check_directory_bindings(workspace_fd: int, codex_fd: int, codex_identity: tuple[int, int, int],
                              agents_identity: tuple[int, int, int]) -> None:
    try:
        codex_info = os.stat(".codex", dir_fd=workspace_fd, follow_symlinks=False)
        agents_info = os.stat("agents", dir_fd=codex_fd, follow_symlinks=False)
    except OSError as exc:
        raise OSError("directory binding changed") from exc
    if any((not stat.S_ISDIR(info.st_mode) or _file_identity(info) != identity)
           for info, identity in ((codex_info, codex_identity), (agents_info, agents_identity))):
        raise OSError("directory binding changed")


def _reject_unexpected_profiles(agents_fd: int) -> None:
    try: names = os.listdir(agents_fd)
    except OSError as exc: raise InstallError("HW_AGENT_INSTALL_FAILED", "cannot inspect profile directory") from exc
    if any(name.casefold().startswith("hwahap-") and name.casefold().endswith(".toml")
           and name not in REQUIRED_PROFILE_NAMES for name in names):
        raise InstallError("HW_AGENT_CONFLICT", "unexpected Hwahap profile")


def lexical_path_has_symlink(path: Path) -> bool:
    current = Path(path.anchor) if path.is_absolute() else Path.cwd()
    for part in path.parts:
        if part in (path.anchor, ""):
            continue
        current /= part
        if current.is_symlink():
            return True
    return False


def install(workspace_arg: str) -> None:
    workspace_path = Path(workspace_arg).expanduser()
    if lexical_path_has_symlink(workspace_path):
        raise InstallError("HW_AGENT_PATH_INVALID", "workspace must use real path components")
    workspace = workspace_path.resolve()
    if not workspace.is_dir():
        raise InstallError("HW_AGENT_PATH_INVALID", "workspace must be a non-symlink directory")

    # Parse every source before creating directories or copying anything.
    profiles = source_profiles()
    workspace_fd = codex_fd = agents_fd = -1
    pending: list[tuple[Path, bytes]] = []
    skipped: list[str] = []
    installed: list[str] = []
    created: list[tuple[str, int | None, str]] = []
    try:
        workspace_fd = _open_directory(None, workspace)
        codex_fd = _open_directory(workspace_fd, ".codex", create=True)
        agents_fd = _open_directory(codex_fd, "agents", create=True)
        codex_identity = _file_identity(os.fstat(codex_fd))
        agents_identity = _file_identity(os.fstat(agents_fd))
        _reject_unexpected_profiles(agents_fd)
        for source, raw in profiles:
            try:
                info = os.stat(source.name, dir_fd=agents_fd, follow_symlinks=False)
            except FileNotFoundError:
                pending.append((source, raw))
                continue
            except OSError as exc:
                raise InstallError("HW_AGENT_PATH_INVALID", "target must be a regular file") from exc
            if not stat.S_ISREG(info.st_mode):
                raise InstallError("HW_AGENT_PATH_INVALID", "target must be a regular file")
            existing = _read_profile_at(agents_fd, source.name)
            if existing == raw:
                skipped.append(source.name)
                continue
            raise InstallError("HW_AGENT_CONFLICT", "different existing profile")
        for source, raw in pending:
            _check_directory_bindings(workspace_fd, codex_fd, codex_identity, agents_identity)
            _reject_unexpected_profiles(agents_fd)
            fd = os.open(source.name, _PROFILE_FLAGS, 0o600, dir_fd=agents_fd)
            created.append((source.name, None, hashlib.sha256(raw).hexdigest()))
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode):
                    raise OSError("created profile is not regular")
                created[-1] = (source.name, os.dup(fd), created[-1][2])
                with os.fdopen(fd, "wb") as handle:
                    handle.write(raw)
            except Exception:
                try:
                    os.close(fd)
                except Exception:
                    pass
                raise
            installed.append(source.name)
        _check_directory_bindings(workspace_fd, codex_fd, codex_identity, agents_identity)
        _reject_unexpected_profiles(agents_fd)
    except FileExistsError as exc:
        complete = not created or (agents_fd >= 0 and cleanup_created(agents_fd, created))
        if not complete:
            raise InstallError("HW_AGENT_INSTALL_FAILED", "profile installation conflict; rollback incomplete") from exc
        raise InstallError("HW_AGENT_CONFLICT", "profile installation conflict") from exc
    except Exception as exc:
        complete = not created or (agents_fd >= 0 and cleanup_created(agents_fd, created))
        message = "profile installation failed" if complete else "profile installation failed; rollback incomplete"
        if isinstance(exc, InstallError) and complete:
            raise
        if isinstance(exc, InstallError) and exc.code == "HW_AGENT_CONFLICT":
            message = "profile installation conflict; rollback incomplete"
        raise InstallError("HW_AGENT_INSTALL_FAILED", message) from exc
    finally:
        for _, guard_fd, _ in created:
            if guard_fd is not None:
                try: os.close(guard_fd)
                except Exception: pass
        for fd in (agents_fd, codex_fd, workspace_fd):
            if fd >= 0:
                try:
                    os.close(fd)
                except Exception:
                    pass
    print(f"HW_OK: installed={len(installed)} skipped={len(skipped)} target={workspace / '.codex' / 'agents'}")


def main(argv: list[str] | None = None) -> int:
    parser = SafeArgumentParser(description=__doc__)
    parser.add_argument("--workspace")
    try:
        args = parser.parse_args(argv)
        if not args.workspace:
            raise InstallError("HW_AGENT_ARGUMENT_INVALID", "--workspace is required")
        install(args.workspace)
    except InstallError as exc:
        code = exc.code if exc.code in PUBLIC_ERROR_MESSAGES else "HW_AGENT_INSTALL_FAILED"
        print(f"{code}: {PUBLIC_ERROR_MESSAGES[code]}", file=sys.stderr)
        return 1
    except (OSError, shutil.Error):
        print("HW_AGENT_INSTALL_FAILED: profile installation failed", file=sys.stderr)
        return 1
    except Exception:
        print("HW_AGENT_INSTALL_FAILED: profile installation failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
