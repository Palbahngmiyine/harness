"""Resolve paths shared by state mutation commands."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())


def command_paths(
        workspace_arg: str, run_id: str) -> tuple[Path, Path, Path, Path]:
    workspace_arg_path = Path(workspace_arg).expanduser()
    if lexical_path_has_symlink(workspace_arg_path):
        raise HwahapError(
            "HW_STATE_INVALID", "workspace must not use symlink components")
    workspace = workspace_arg_path.resolve()
    _, run_dir = state_paths(workspace, run_id)
    validate_recovery_boundary(run_dir, recover=True)
    return workspace, run_dir, run_dir / "contract.json", run_dir / "run.json"


def validate_recovery_boundary(run_dir: Path, *, recover: bool) -> None:
    validate_state_directory(run_dir, "run")
    validate_state_directory(run_dir / "units", "units")
    if recover:
        _recover_report_transaction(run_dir)
