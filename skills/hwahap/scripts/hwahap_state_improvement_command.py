"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def record_improvement(args: argparse.Namespace) -> None:
    unit_id = require_safe_unit_id(args.unit_id)
    workspace, run_dir, _, run_path = command_paths(args.workspace, args.run_id)
    validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    unit_path = run_dir / "units" / f"{unit_id}.json"
    events_path = run_dir / "events.jsonl"
    for label, path in (("unit", unit_path), ("events.jsonl", events_path)):
        if path.is_symlink() or not path.is_file():
            raise HwahapError("HW_STATE_INVALID", f"{label} must be a regular file")
    require_run_unit_mutation_allowed(run_path)
    unit = read_json(unit_path)
    run = read_json(run_path)
    history = unit.get("improvement_history")
    if not isinstance(history, list):
        raise HwahapError("HW_STATE_INVALID", "improvement_history must be a list")
    if unit.get("status") != "reviewing" or not required_text(args.actor):
        raise HwahapError("HW_STATE_INVALID", "record-improvement requires a reviewing unit and actor")
    target = "recovery" if args.kind == "terra_recovery" else "replan_required"
    if args.kind not in {"terra_recovery", "sol_replan", "recursive_improvement"}:
        raise HwahapError("HW_STATE_INVALID", "invalid improvement kind")
    record = {
        "after_round": args.after_round, "kind": args.kind,
        "failure_signature": args.failure_signature, "root_cause": args.root_cause,
        "hypothesis": args.hypothesis, "action": args.action,
        "strategy_digest": args.strategy_digest, "scope_status": args.scope_status,
        "evidence": args.evidence_ref,
    }
    try:
        original_unit, original_run, original_events = (
            unit_path.read_bytes(), run_path.read_bytes(), events_path.read_bytes())
        event_lines = [line for line in original_events.decode("utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeDecodeError) as exc:
        raise HwahapError("HW_STATE_INVALID", "cannot read state files") from exc
    history.append(record)
    unit["replan_count"] = sum(
        item.get("kind") in {"sol_replan", "recursive_improvement"}
        for item in history if isinstance(item, dict)
    )
    unit["status"] = target
    if target == "replan_required":
        unit["failure"] = {
            "code": "HW_REPLAN_REQUIRED", "reason": args.root_cause,
            "evidence": args.evidence_ref, "recovery": args.action,
        }
    run_target = "recovering" if target == "recovery" else "replanning"
    event = {
        "timestamp": utc_now(), "type": "state_transition", "sequence": len(event_lines) + 1,
        "entity": unit_id, "from": "reviewing", "to": target,
        "actor": args.actor, "role": "orchestrator", "reason": args.action,
        "input_digest": args.strategy_digest, "evidence_refs": args.evidence_ref,
        "review_round": args.after_round,
    }
    run_event = dict(event, entity="run", from_=run.get("status", ""), to=run_target)
    run_event["from"] = run_event.pop("from_")
    run_event["sequence"] = len(event_lines) + 1
    event["sequence"] += 1
    try:
        write_json(unit_path, unit)
        run["status"] = run_target
        write_json(run_path, run)
        events_path.write_bytes(original_events + (json.dumps(run_event, ensure_ascii=False) + "\n").encode("utf-8")
                                + (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8"))
        validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    except Exception as exc:
        restore_state_files(((unit_path, original_unit), (run_path, original_run), (events_path, original_events)))
        if isinstance(exc, HwahapError):
            raise
        raise HwahapError("HW_STATE_INVALID", "could not update improvement state") from exc
    print(f"HW_OK: run={args.run_id} unit={unit_id} improvement={args.after_round}")
