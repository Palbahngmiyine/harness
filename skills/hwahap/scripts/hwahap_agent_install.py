"""Install validated agent profiles with rollback on partial writes."""

from pathlib import Path

from hwahap_agent_contract import (
    InstallError, REQUIRED_PROFILE_NAMES, is_hwahap_profile_name,
)
from hwahap_agent_profiles import lexical_path_has_symlink


def _rollback(paths: list[Path]) -> bool:
    complete = True
    for path in paths:
        try:
            path.unlink()
        except OSError:
            complete = False
    return complete


def _agent_directory(workspace_arg: str) -> Path:
    workspace = Path(workspace_arg).expanduser()
    if lexical_path_has_symlink(workspace) or not workspace.is_dir():
        raise InstallError("HW_AGENT_PATH_INVALID", "workspace is invalid")
    codex, agents = workspace / ".codex", workspace / ".codex" / "agents"
    for target in (codex, agents):
        if target.exists() and (target.is_symlink() or not target.is_dir()):
            raise InstallError("HW_AGENT_PATH_INVALID", "agent directory is invalid")
    try:
        agents.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise InstallError(
            "HW_AGENT_INSTALL_FAILED", "cannot create agent directory") from None
    return agents


def _plan(agents: Path, profiles: list[tuple[Path, bytes]]) -> tuple[list, int]:
    names = {path.name for path in agents.iterdir()}
    unexpected = any(is_hwahap_profile_name(name)
                     and name not in REQUIRED_PROFILE_NAMES for name in names)
    if unexpected:
        raise InstallError("HW_AGENT_CONFLICT", "unexpected Hwahap profile")
    pending, skipped = [], 0
    for source, raw in profiles:
        target = agents / source.name
        if target.is_symlink() or target.exists() and not target.is_file():
            raise InstallError("HW_AGENT_PATH_INVALID", "target must be a regular file")
        if not target.exists():
            pending.append((target, raw))
        elif target.read_bytes() != raw:
            raise InstallError("HW_AGENT_CONFLICT", "different existing profile")
        else:
            skipped += 1
    return pending, skipped


def install_profiles(workspace_arg: str, profiles: list[tuple[Path, bytes]]) -> None:
    agents = _agent_directory(workspace_arg)
    pending, skipped = _plan(agents, profiles)
    created = []
    try:
        for target, raw in pending:
            with target.open("xb") as handle:
                handle.write(raw)
            created.append(target)
    except FileExistsError as error:
        _rollback(created)
        raise InstallError(
            "HW_AGENT_CONFLICT", "profile installation conflict") from error
    except Exception as error:
        complete = _rollback(created)
        message = ("profile installation failed" if complete
                   else "profile installation failed; rollback incomplete")
        raise InstallError("HW_AGENT_INSTALL_FAILED", message) from error
    print(f"HW_OK: installed={len(pending)} skipped={skipped} target={agents}")
