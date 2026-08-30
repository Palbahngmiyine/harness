"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def _validate_run_units(unit_files: list, contract: dict, forbidden: object,
                        errors: list[str], workspace: Path) -> tuple[list, list]:
    units, histories, seen, execution_receipts = [], [], set(), set()
    for _, _, unit in unit_files:
        units.append(unit)
        histories.append(validate_unit(unit, contract, seen, errors, workspace))
        receipts = unit.get("test_receipts")
        for receipt in receipts if isinstance(receipts, list) else []:
            if not isinstance(receipt, dict):
                continue
            digest = receipt.get("execution_receipt_sha256")
            if isinstance(digest, str) and digest in execution_receipts:
                errors.append("duplicate execution receipt across units")
            elif isinstance(digest, str):
                execution_receipts.add(digest)
        unit_paths = unit.get("allowed_paths")
        for unit_path in unit_paths if isinstance(unit_paths, list) else []:
            if not safe_relative_path(unit_path):
                errors.append(f"{unit.get('unit_id')}: unsafe allowed path")
            if isinstance(forbidden, list) and isinstance(unit_path, str) and any(
                    isinstance(item, str) and paths_overlap(unit_path, item)
                    for item in forbidden):
                errors.append(f"{unit.get('unit_id')}: allowed path overlaps forbidden_changes")
    if len([unit for unit in units if unit.get("status") not in {"planned", "passed"}]) > 1:
        errors.append("only one unit may be unresolved")
    return units, histories


def _validate_completed_run(run: dict, units: list, locked: object, events_path: Path,
                            workspace: Path, errors: list[str]) -> None:
    if not locked or not units or any(unit.get("status") != "passed" for unit in units):
        errors.append("completed run requires a locked contract and all units passed")
    goal_link = run.get("goal_link")
    current = goal_link.get("current") if isinstance(goal_link, dict) else None
    if isinstance(current, dict) and current.get("mode") == "unobserved":
        errors.append("completed run requires an observed Goal link")
    final = run.get("final_review")
    if not required_text(run.get("completed_at")) or not isinstance(final, dict) \
            or final.get("status") != "pass":
        errors.append("completed run requires final review pass and completed_at")
    digest = final_review_passing_digest(final, workspace)
    if digest is None:
        errors.append("completed run requires a valid final passing review digest")
        return
    try:
        events = parse_events(events_path)
    except (OSError, UnicodeError, json.JSONDecodeError):
        events = []
    if not events or events[-1].get("input_digest") != digest:
        errors.append("completed run input digest does not match final review digest")
