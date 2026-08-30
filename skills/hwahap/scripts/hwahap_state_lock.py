"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def transition_event(sequence: int, entity: str, source: str, target: str,
                     args: argparse.Namespace) -> dict:
    return {
        "timestamp": utc_now(), "type": "state_transition", "sequence": sequence,
        "entity": entity, "from": source, "to": target, "actor": args.actor,
        "role": args.role, "reason": args.reason, "input_digest": args.input_digest,
        "evidence_refs": args.evidence_ref, "review_round": args.review_round,
    }


def lock_contract(args: argparse.Namespace) -> None:
    workspace, run_dir, contract_path, run_path = command_paths(args.workspace, args.run_id)
    validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    contract, run = read_json(contract_path), read_json(run_path)
    events_path = run_dir / "events.jsonl"
    if contract.get("locked") or run.get("status") != "initialized" or events_path.read_text(encoding="utf-8").strip():
        raise HwahapError("HW_STATE_INVALID", "contract lock requires a fresh initialized run")
    current_goal = run.get("goal_link", {}).get("current", {}) if isinstance(run.get("goal_link"), dict) else {}
    if not isinstance(current_goal, dict) or current_goal.get("mode") != "bound":
        raise HwahapError("HW_GOAL_REQUIRED", "runs require a bound Goal before locking")
    if any(not isinstance(contract.get(field), list) or not contract[field] for field in CONTRACT_LISTS):
        raise HwahapError("HW_STATE_INVALID", "fill every contract list before locking")
    if any(not safe_test_command(command) for command in contract["test_commands"]):
        raise HwahapError("HW_STATE_INVALID", "credential-bearing test command is unsafe")
    original = (
        (contract_path, contract_path.read_bytes()),
        (run_path, run_path.read_bytes()),
        (events_path, events_path.read_bytes()),
    )
    contract["locked"] = True
    contract["lock_sha256"] = canonical_contract_digest(contract)
    run["status"] = "contract_locked"
    event = transition_event(1, "run", "initialized", "contract_locked", argparse.Namespace(
        actor=args.actor, role="orchestrator", reason=args.reason,
        input_digest=contract["lock_sha256"], evidence_ref=args.evidence_ref, review_round=0,
    ))
    try:
        write_json(contract_path, contract)
        write_json(run_path, run)
        events_path.write_text(json.dumps(event, ensure_ascii=False) + "\n", encoding="utf-8")
        validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    except Exception as exc:
        restore_state_files(original)
        if isinstance(exc, HwahapError):
            raise
        raise HwahapError("HW_STATE_INVALID", "could not update contract state") from exc
    print(f"HW_OK: run={args.run_id} contract_locked digest={contract['lock_sha256']}")


def require_run_unit_mutation_allowed(run_path: Path) -> dict:
    run = read_json(run_path)
    if run.get("status") in RUN_UNIT_MUTATION_BLOCKED_STATES:
        raise HwahapError("HW_STATE_INVALID", "unit mutation is forbidden after final_review or run termination")
    return run


def require_safe_unit_id(unit_id: object) -> str:
    if not isinstance(unit_id, str) or not SLUG.fullmatch(unit_id):
        raise HwahapError("HW_STATE_INVALID", "unsafe unit ID")
    return unit_id


def require_single_implementing_unit(run_dir: Path, unit_id: str) -> None:
    active = []
    for path in sorted((run_dir / "units").glob("*.json")):
        unit = read_json(path)
        if unit.get("unit_id") != unit_id and unit.get("status") not in {"planned", "passed"}:
            active.append(str(unit.get("unit_id")))
    if active:
        raise HwahapError("HW_STATE_INVALID", "only one unit may be unresolved")
