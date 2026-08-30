"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def transition(args: argparse.Namespace) -> None:
    workspace, run_dir, contract_path, run_path = command_paths(args.workspace, args.run_id)
    validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    if args.entity == "run" and args.to == "completed":
        raise HwahapError("HW_STATE_INVALID", "use complete command to finish a run")
    events_path = run_dir / "events.jsonl"
    if args.entity == "run":
        state_path = run_path
        graph = RUN_TRANSITIONS
    else:
        require_run_unit_mutation_allowed(run_path)
        entity = require_safe_unit_id(args.entity)
        state_path = run_dir / "units" / f"{entity}.json"
        graph = UNIT_TRANSITIONS
    state = read_json(state_path)
    source = state.get("status")
    if not isinstance(source, str) or args.to not in graph.get(source, set()):
        raise HwahapError("HW_STATE_INVALID", f"illegal transition: {source} -> {args.to}")
    if args.entity != "run" and args.to == "implementing":
        require_single_implementing_unit(run_dir, args.entity)
    if args.entity == "run" and args.to == "final_review":
        contract = read_json(contract_path)
        units = [unit for _, _, unit in read_unit_files(run_dir / "units")]
        final_errors: list[str] = []
        validate_final_review_units(units, contract, final_errors, workspace)
        if final_errors:
            raise HwahapError("HW_STATE_INVALID", "; ".join(final_errors))
    if args.entity == "run" and source == "final_review" and args.to == "awaiting_user":
        final = state.get("final_review")
        final_errors: list[str] = []
        validate_final_review(final, False, final_errors, workspace)
        expected_code = final_review_failure_code(final)
        if (not isinstance(final, dict) or final.get("status") != "fail" or final_errors
                or expected_code is None or args.failure_code != expected_code):
            raise HwahapError("HW_STATE_INVALID", "final_review awaiting_user requires matching failure evidence")
    if args.to in RUN_FAILURE_STATES | FAILURE_STATES:
        if not all((args.failure_code, args.failure_reason, args.failure_recovery, args.failure_evidence)):
            raise HwahapError("HW_STATE_INVALID", "failure transition requires code, reason, evidence, and recovery")
        state["failure"] = {
            "code": args.failure_code, "reason": args.failure_reason,
            "evidence": args.failure_evidence, "recovery": args.failure_recovery,
        }
    if args.entity == "run" and args.to == "completed":
        state["completed_at"] = utc_now()
    event_lines = [line for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    event = transition_event(len(event_lines) + 1, args.entity, source, args.to, args)
    state["status"] = args.to
    if args.entity == "run" and args.to in RUN_TERMINAL_STATES:
        publish_terminal_report(workspace, run_dir, contract_path, run_path, state, event)
        print(f"HW_OK: run={args.run_id} entity=run state={args.to} report={run_dir / 'report.html'}")
        return
    original = ((state_path, state_path.read_bytes()), (events_path, events_path.read_bytes()))
    try:
        write_json(state_path, state)
        events_path.write_text(original[1][1].decode("utf-8") + json.dumps(event, ensure_ascii=False) + "\n", encoding="utf-8")
        validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    except Exception as exc:
        restore_state_files(original)
        if isinstance(exc, HwahapError):
            raise
        raise HwahapError("HW_STATE_INVALID", "could not update state") from exc
    print(f"HW_OK: run={args.run_id} entity={args.entity} state={args.to}")
