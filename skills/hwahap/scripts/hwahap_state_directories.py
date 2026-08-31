"""Private directory creation and validation for Hwahap state."""
from __future__ import annotations

from hwahap_state_runtime import *
register(globals())

_PRIVATE_MODE = 0o700


def _safe_directory(path: Path) -> bool:
    try:
        info = path.stat(follow_symlinks=False)
    except OSError:
        return False
    return (stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == _PRIVATE_MODE
            and not path.is_symlink())


def validate_state_directory(path: Path, label: str) -> None:
    if not _safe_directory(path):
        raise HwahapError("HW_STATE_INVALID", f"{label} must be a safe directory")


def _create_directory(path: Path, created: list[Path], private: bool = False) -> None:
    if path.is_symlink():
        raise HwahapError("HW_STATE_INVALID", "state directory is unsafe")
    if path.exists():
        if not path.is_dir():
            raise HwahapError("HW_STATE_INVALID", "state directory is unsafe")
        return
    path.mkdir(mode=_PRIVATE_MODE if private else 0o777)
    created.append(path)
    if private:
        path.chmod(_PRIVATE_MODE)
        validate_state_directory(path, "state directory")


def create_state_directories(workspace: Path, run_dir: Path) -> tuple[Path, ...]:
    created: list[Path] = []
    parent_dirs = (workspace / ".hwahap", workspace / ".hwahap" / "runs")
    try:
        for path in parent_dirs:
            _create_directory(path, created)
        _create_directory(run_dir, created, private=True)
        _create_directory(run_dir / "units", created, private=True)
        validate_state_directory(run_dir, "run")
        validate_state_directory(run_dir / "units", "units")
        return tuple(created)
    except Exception:
        for path in reversed(created):
            remove_path_best_effort(path)
        raise
