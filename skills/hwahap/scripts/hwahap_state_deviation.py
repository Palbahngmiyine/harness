"""Atomic recording of complete causal v4 deviations."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())


def record_deviation(args: argparse.Namespace) -> None:
    workspace, run_dir, _, run_path = command_paths(args.workspace, args.run_id)
    validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    run = read_json(run_path)
    if run.get("status") in RUN_TERMINAL_STATES:
        raise HwahapError("HW_STATE_INVALID", "cannot record a deviation after run termination")
    record = {
        "summary": args.summary, "root_cause": args.root_cause,
        "impact": args.impact, "prevention": args.prevention,
        "evidence_explanation": args.evidence_explanation,
        "evidence": args.evidence,
    }
    errors: list[str] = []
    validate_deviations([record], errors)
    validate_state_strings(record, "deviation", errors)
    if errors:
        raise HwahapError("HW_STATE_INVALID", "deviation must be a complete causal v4 record")
    original = ((run_path, run_path.read_bytes()),)
    deviations = run.get("deviations")
    if not isinstance(deviations, list):
        raise HwahapError("HW_STATE_INVALID", "deviations must be a list")
    deviations.append(record)
    run["metrics"]["scope_deviations"] = len(deviations)
    try:
        write_json(run_path, run)
        validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    except Exception as exc:
        restore_state_files(original)
        if isinstance(exc, HwahapError):
            raise
        raise HwahapError("HW_STATE_INVALID", "could not record deviation") from exc
    print(f"HW_OK: run={args.run_id} deviation={len(deviations)}")
