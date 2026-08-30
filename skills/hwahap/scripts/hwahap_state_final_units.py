"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def validate_final_review_units(units: list[dict], contract: dict, errors: list[str], workspace: Path | None = None) -> None:
    if not units:
        errors.append("final_review requires at least one passed unit")
        return
    seen: set[str] = set()
    for unit in units:
        if unit.get("status") != "passed":
            errors.append(f"{unit.get('unit_id')}: final_review requires a passed unit")
        validate_unit(unit, contract, seen, errors, workspace)


def validate_final_review_snapshot_chain(final: object, units: list[dict], events: list[dict],
                                         errors: list[str]) -> None:
    """Validate the passed-unit chain and bind every final snapshot to it."""
    attempts = final.get("attempts", []) \
        if isinstance(final, dict) and isinstance(final.get("attempts"), list) else []
    passed_units = [unit for unit in units if isinstance(unit, dict) and unit.get("status") == "passed"]
    pass_events = [event for event in events
                   if isinstance(event, dict) and event.get("entity") != "run"
                   and event.get("to") == "passed"]
    event_ids = [event.get("entity") for event in pass_events]
    unit_ids = [unit.get("unit_id") for unit in passed_units]
    if (not pass_events or any(not isinstance(item, str) for item in event_ids)
            or len(event_ids) != len(set(event_ids))
            or len(pass_events) != len(passed_units) or set(event_ids) != set(unit_ids)
            or any(not isinstance(event.get("sequence"), int) for event in pass_events)):
        errors.append("final_review passed-unit event order or mapping is invalid")
        return

    by_id = {unit.get("unit_id"): unit for unit in passed_units}
    snapshots: list[dict] = []
    for unit_id in event_ids:
        unit = by_id.get(unit_id)
        history = unit.get("review_history") if isinstance(unit, dict) else None
        review = history[-1] if isinstance(history, list) and history else None
        snapshot = review.get("diff_snapshot") if isinstance(review, dict) else None
        if not isinstance(snapshot, dict):
            errors.append("final_review passed unit is missing its latest passing snapshot")
            return
        snapshots.append(snapshot)
    for previous, current in zip(snapshots, snapshots[1:]):
        if (previous.get("target_commit"), previous.get("target_tree")) != (
                current.get("base_commit"), current.get("base_tree")):
            errors.append("final_review passed-unit snapshots are not an adjacent chain")
            return

    first, last = snapshots[0], snapshots[-1]
    for attempt in attempts:
        if not isinstance(attempt, dict):
            continue
        snapshot = attempt.get("diff_snapshot")
        if not isinstance(snapshot, dict) or (
                snapshot.get("base_commit"), snapshot.get("base_tree")) != (
                first.get("base_commit"), first.get("base_tree")) or (
                snapshot.get("target_commit"), snapshot.get("target_tree")) != (
                last.get("target_commit"), last.get("target_tree")):
            errors.append("final_review passing snapshot does not span the passed-unit chain")
