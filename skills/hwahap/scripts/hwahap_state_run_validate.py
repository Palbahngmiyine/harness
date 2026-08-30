"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def validate_run(args: argparse.Namespace) -> None:
    workspace_arg = Path(args.workspace).expanduser()
    if lexical_path_has_symlink(workspace_arg):
        raise HwahapError("HW_STATE_INVALID", "workspace must not use symlink components")
    workspace = workspace_arg.resolve()
    hwahap, run_dir = state_paths(workspace, args.run_id)
    if not getattr(args, "_skip_recovery", False):
        _recover_report_transaction(run_dir)
    units_dir = run_dir / "units"
    required = [run_dir / "contract.json", run_dir / "run.json", run_dir / "events.jsonl"]
    for label, path in ((".hwahap", hwahap), ("runs", hwahap / "runs"), ("run", run_dir), ("units", units_dir)):
        if path.is_symlink() or not path.is_dir():
            raise HwahapError("HW_STATE_INVALID", f"{label} must be a real directory")
    for path in required:
        if not _single_regular_file(path):
            raise HwahapError("HW_STATE_INVALID", f"{path.name} must be a real file")
    contract, run = read_json(required[0]), read_json(required[1])
    errors: list[str] = []
    validate_state_strings(contract, "contract", errors, skip_command_fields=True)
    validate_state_strings(run, "run", errors)
    unit_files = read_unit_files(units_dir)
    for path, _, unit in unit_files:
        if unit.get("unit_id") != path.stem:
            errors.append("unit filename does not match internal unit_id")
        validate_state_strings(unit, f"unit {path.stem}", errors, skip_command_fields=True)
    try:
        for index, event in enumerate(parse_events(required[2]), 1):
            validate_state_strings(event, f"events.jsonl line {index}", errors)
    except (OSError, UnicodeError, json.JSONDecodeError):
        pass
    if errors:
        raise HwahapError("HW_STATE_INVALID", "credential-bearing state value is unsafe")
    status, locked, forbidden = _validate_run_contract(
        args, workspace, contract, run, errors)
    units, histories = _validate_run_units(
        unit_files, contract, forbidden, errors, workspace)
    if (any(has_pending_improvement(unit) for unit in units)
            and status not in ({"reviewing", "cancelled"} | RUN_FAILURE_STATES)):
        errors.append(
            "pending improvement requires reviewing, cancelled, or terminal failure")
    events = validate_events(required[2], run, units, errors)
    validate_final_review_lifecycle(run, units, contract, events, errors, workspace)
    last_event = events[-1] if events else {}
    if (status == "awaiting_user" and last_event.get("entity") == "run"
            and last_event.get("from") == "final_review" and last_event.get("to") == "awaiting_user"):
        expected_code = final_review_failure_code(run.get("final_review"))
        failure = run.get("failure")
        if expected_code is None or not isinstance(failure, dict) or failure.get("code") != expected_code:
            errors.append("final_review awaiting_user has invalid failure code")
    deviations = run.get("deviations")
    deferred = run.get("deferred_security")
    validate_records(deviations, ("summary", "root_cause", "impact", "prevention"), "deviations", errors)
    validate_records(deferred, ("summary", "reason", "next_action"), "deferred_security", errors)
    validate_metrics(run, units, histories, deviations if isinstance(deviations, list) else [], errors)
    final_review_errors: list[str] = []
    final = run.get("final_review")
    validate_final_review(final, status == "completed", final_review_errors, workspace)
    errors.extend(final_review_errors)
    candidates = run.get("improvement_candidates")
    if isinstance(candidates, list) and candidates and (
            not isinstance(final, dict) or final.get("status") != "pass" or final_review_errors):
        errors.append("improvement_candidates require a valid passing final_review")
    validate_report_schema(run, run_dir, contract, units, errors)
    if status == "completed":
        _validate_completed_run(run, units, locked, required[2], workspace, errors)
    if errors:
        raise HwahapError("HW_STATE_INVALID", "; ".join(errors))
    if not getattr(args, "quiet", False):
        print(f"HW_OK: run={args.run_id} status={run['status']} units={len(units)}")
