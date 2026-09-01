"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def add_unit(args: argparse.Namespace) -> None:
    unit_id = require_safe_unit_id(args.unit_id)
    title = getattr(args, "title", None)
    if not required_text(title) or credential_bearing_text(title):
        raise HwahapError("HW_STATE_INVALID", "unit title is invalid")
    workspace, run_dir, contract_path, run_path = command_paths(args.workspace, args.run_id)
    validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    require_run_unit_mutation_allowed(run_path)
    contract, run = read_json(contract_path), read_json(run_path)
    if not contract.get("locked") or run.get("status") != "contract_locked":
        raise HwahapError("HW_STATE_INVALID", "unit creation requires a locked contract and safe unit ID")
    if (not isinstance(args.allowed_path, list) or not args.allowed_path
            or any(not safe_relative_path(path) or credential_bearing_text(path)
                   for path in args.allowed_path)):
        raise HwahapError("HW_STATE_INVALID", "unsafe unit allowed path")
    if (not isinstance(args.acceptance_command, list) or not args.acceptance_command
            or any(not safe_test_command(command) for command in args.acceptance_command)):
        raise HwahapError("HW_STATE_INVALID", "credential-bearing acceptance command is unsafe")
    drift_paths = [path for path in args.allowed_path if path not in contract["allowed_paths"]]
    drift_commands = [command for command in args.acceptance_command if command not in contract["test_commands"]]
    if drift_paths or drift_commands:
        record_add_unit_scope_drift(run_dir, run_path, args, drift_paths, drift_commands)
    unit_path = run_dir / "units" / f"{unit_id}.json"
    if unit_path.exists() or unit_path.is_symlink():
        raise HwahapError("HW_STATE_INVALID", f"unit already exists: {args.unit_id}")
    trace = source_unit_trace(contract, getattr(args, "source_unit_id", None))
    unit = {
        "unit_id": unit_id, "title": title, "status": "planned",
        "source_trace": trace,
        "writer": "hwahap-luna-implementer", "allowed_paths": args.allowed_path,
        "acceptance_commands": args.acceptance_command, "replan_count": 0,
        "review_history": [], "improvement_history": [], "recovery": None, "failure": None,
        "test_receipts": [],
    }
    try:
        original_run = run_path.read_bytes()
    except Exception as exc:
        raise HwahapError("HW_STATE_INVALID", "could not snapshot unit state") from exc
    try:
        write_json(unit_path, unit)
        run["metrics"]["unit_count"] = len(list((run_dir / "units").glob("*.json")))
        write_json(run_path, run)
        validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    except Exception as exc:
        restore_state_files(((run_path, original_run),))
        remove_path_best_effort(unit_path)
        raise HwahapError("HW_STATE_INVALID", "could not create unit") from exc
    print(f"HW_OK: run={args.run_id} unit={args.unit_id} planned")
