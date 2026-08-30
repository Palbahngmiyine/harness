"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())


def complete_run(args: argparse.Namespace) -> None:
    workspace, run_dir, contract_path, run_path = command_paths(
        args.workspace, args.run_id)
    validate_run(argparse.Namespace(
        workspace=str(workspace), run_id=args.run_id, quiet=True))
    events_path = run_dir / "events.jsonl"
    contract, run = read_json(contract_path), read_json(run_path)
    units = [unit for _, _, unit in read_unit_files(run_dir / "units")]
    final_errors: list[str] = []
    final = run.get("final_review")
    validate_final_review(final, True, final_errors, workspace)
    final_status = final.get("status") if isinstance(final, dict) else None
    goal_link = run.get("goal_link")
    goal = goal_link.get("current") if isinstance(goal_link, dict) else None
    ready = (run.get("status") == "final_review"
             and final_status == "pass" and not final_errors
             and contract.get("locked") and units
             and all(unit.get("status") == "passed" for unit in units))
    if not ready:
        raise HwahapError(
            "HW_STATE_INVALID",
            "complete requires a valid final_review, locked contract, and passed units")
    final_digest = final_review_passing_digest(final, workspace)
    if (not isinstance(args.input_digest, str)
            or not SHA256.fullmatch(args.input_digest)
            or args.input_digest != final_digest):
        raise HwahapError(
            "HW_STATE_INVALID",
            "complete input digest must match the final passing review digest")
    if not isinstance(goal, dict) or goal.get("mode") != "bound":
        raise HwahapError(
            "HW_GOAL_REQUIRED", "complete requires a bound Goal")
    events = parse_events(events_path)
    event = transition_event(
        len(events) + 1, "run", "final_review", "completed",
        argparse.Namespace(
            actor=args.actor, role="orchestrator", reason=args.reason,
            input_digest=args.input_digest, evidence_ref=args.evidence_ref,
            review_round=0))
    working = json.loads(json.dumps(run))
    working.update({"status": "completed", "completed_at": event["timestamp"]})
    try:
        publish_terminal_report(
            workspace, run_dir, contract_path, run_path, working, event,
            operation="complete")
    except Exception:
        raise HwahapError(
            "HW_REPORT_GENERATION_FAILED",
            "could not generate completed report") from None
    print(f"HW_OK: run={args.run_id} completed report={run_dir / 'report.html'}")
