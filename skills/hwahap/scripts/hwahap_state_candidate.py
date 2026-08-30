"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def validate_improvement_candidate(record: object, label: str, errors: list[str]) -> None:
    if not isinstance(record, dict):
        errors.append(f"{label} must be an object")
        return
    if set(record) != CANDIDATE_FIELDS:
        errors.append(f"{label} has invalid fields")
    if record.get("status") != "proposed":
        errors.append(f"{label}.status must be proposed")
    if any(not required_text(record.get(field)) for field in ("summary", "expected_effect", "next_action")):
        errors.append(f"{label} requires summary, expected_effect, and next_action")
    evidence = record.get("evidence")
    if not isinstance(evidence, list) or not evidence or any(not required_text(item) for item in evidence):
        errors.append(f"{label}.evidence must be nonempty")


def validate_improvement_candidates(value: object, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append("improvement_candidates must be a list")
        return
    for index, record in enumerate(value, 1):
        validate_improvement_candidate(record, f"improvement_candidates[{index}]", errors)


def record_improvement_candidate(args: argparse.Namespace) -> None:
    workspace, _, _, run_path = command_paths(args.workspace, args.run_id)
    validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    run = read_json(run_path)
    if run.get("status") != "final_review":
        raise HwahapError("HW_STATE_INVALID", "record-improvement-candidate requires a final_review run")
    final = run.get("final_review")
    final_errors: list[str] = []
    validate_final_review(final, False, final_errors, workspace)
    if not isinstance(final, dict) or final.get("status") != "pass" or final_errors:
        raise HwahapError("HW_STATE_INVALID", "record-improvement-candidate requires a valid passing final_review")
    record = {
        "status": "proposed", "summary": args.summary, "evidence": args.evidence_ref,
        "expected_effect": args.expected_effect, "next_action": args.next_action,
    }
    candidate_errors: list[str] = []
    validate_improvement_candidate(record, "improvement_candidate", candidate_errors)
    credential_errors: list[str] = []
    validate_state_strings(record, "improvement_candidate", credential_errors)
    if credential_errors:
        raise HwahapError("HW_STATE_INVALID", "credential-bearing state value is unsafe")
    if candidate_errors:
        raise HwahapError("HW_STATE_INVALID", "; ".join(candidate_errors))
    candidates = run.get("improvement_candidates")
    if not isinstance(candidates, list):
        raise HwahapError("HW_STATE_INVALID", "improvement_candidates must be a list")
    original = run_path.read_bytes()
    try:
        candidates.append(record)
        write_json(run_path, run)
        validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    except Exception as exc:
        restore_state_files(((run_path, original),))
        raise HwahapError("HW_STATE_INVALID", "could not record improvement candidate") from exc
    print(f"HW_OK: run={args.run_id} improvement_candidate=proposed")
