"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def init_run(args: argparse.Namespace) -> None:
    workspace, spec, meta, digest, agent_profiles, _ = _init_input(args)
    _, run_dir = state_paths(workspace, args.goal_id)
    contract_path = run_dir / "contract.json"
    if run_dir.exists():
        units_dir = run_dir / "units"
        for path in (contract_path, run_dir / "run.json", run_dir / "events.jsonl"):
            if path.is_symlink() or (path.exists() and not path.is_file()):
                raise HwahapError("HW_STATE_INVALID", f"{path.name} must be a real file")
        if units_dir.is_symlink() or (units_dir.exists() and not units_dir.is_dir()):
            raise HwahapError("HW_STATE_INVALID", "units must be a real directory")
        if units_dir.is_dir():
            read_unit_files(units_dir)
        if contract_path.is_file():
            existing = read_json(contract_path)
            existing_spec = existing.get("spec")
            if not isinstance(existing_spec, dict):
                raise HwahapError("HW_STATE_INVALID", "spec must be an object")
            if existing_spec.get("sha256") == digest:
                validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.goal_id, quiet=True))
                print(f"HW_OK: run={args.goal_id} already initialized")
                return
        raise HwahapError("HW_RUN_EXISTS", f"run {args.goal_id} already exists with different state")
    source = str(spec.relative_to(workspace)) if spec.is_relative_to(workspace) else str(spec)
    contract, run = _initial_state(args.goal_id, meta, source, digest,
                                   agent_profiles, utc_now())
    initial_errors: list[str] = []
    validate_state_strings(contract, "contract", initial_errors)
    validate_state_strings(run, "run", initial_errors)
    if initial_errors:
        raise HwahapError("HW_STATE_INVALID", "initial state contains credential-bearing text")
    _write_initial_state(workspace, run_dir, contract, run)
    print(f"HW_OK: run={args.goal_id} initialized path={run_dir}")
