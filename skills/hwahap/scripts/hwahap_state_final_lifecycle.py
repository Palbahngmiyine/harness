"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def validate_final_review_lifecycle(run: dict, units: list[dict], contract: dict,
                                   events: list[dict], errors: list[str], workspace: Path) -> None:
    status = run.get("status")
    final = run.get("final_review")
    initial_final = isinstance(final, dict) and final.get("status") == "pending" and final.get("attempts") == []
    run_events = [(index, event) for index, event in enumerate(events)
                  if event.get("entity") == "run"]
    entries = [(index, event) for index, event in run_events if event.get("to") == "final_review"]
    exits = [(index, event) for index, event in run_events if event.get("from") == "final_review"]
    final_failure_claim = isinstance(run.get("failure"), dict) and run["failure"].get("code") == "HW_FINAL_REVIEW_FAILED"
    claim = ((isinstance(status, str) and status in {"final_review", "completed"})
             or bool(entries) or bool(exits) or not initial_final or final_failure_claim)
    if not claim:
        return
    validate_final_review_snapshot_scope(final, contract, units, errors)
    if (not isinstance(status, str) or status not in {"final_review", "completed", "awaiting_user"}) and not entries and not exits:
        errors.append("final_review claim is invalid before final review")
        validate_final_review_units(units, contract, errors, workspace)
        return
    if len(entries) != 1:
        errors.append("final_review requires exactly one entry event")
    if entries and exits and entries[0][0] > exits[0][0]:
        errors.append("final_review entry must precede its exit")
    if status == "final_review":
        if exits:
            errors.append("final_review status cannot have an exit event")
        if final_failure_claim:
            errors.append("final review failure requires awaiting_user")
        valid_errors: list[str] = []
        validate_final_review(final, False, valid_errors, workspace)
        if valid_errors:
            errors.append("final_review aggregate is invalid")
    elif status == "completed":
        if len(exits) != 1 or exits[0][1].get("to") != "completed":
            errors.append("completed run requires one final_review completion exit")
        if final_failure_claim:
            errors.append("completed run cannot claim final review failure")
        valid_errors = []
        validate_final_review(final, True, valid_errors, workspace)
        if valid_errors:
            errors.append("completed run requires a passing final_review aggregate")
    elif status == "awaiting_user" and entries:
        if len(exits) != 1 or exits[0][1].get("to") != "awaiting_user":
            errors.append("awaiting_user after final_review requires one failure exit")
        valid_errors = []
        validate_final_review(final, False, valid_errors, workspace)
        expected = final_review_failure_code(final)
        failure = run.get("failure")
        if valid_errors or expected is None or not isinstance(failure, dict) or failure.get("code") != expected:
            errors.append("awaiting_user final_review failure evidence is invalid")
    elif status == "cancelled" and entries:
        if len(exits) != 1 or exits[0][1].get("to") != "cancelled":
            errors.append("cancelled final_review requires one cancellation exit")
        valid_errors = []
        validate_final_review(final, False, valid_errors, workspace)
        if valid_errors:
            errors.append("cancelled final_review aggregate is invalid")
    elif entries or exits:
        errors.append("final_review events do not match the current run status")
    if entries or exits or status in {"final_review", "completed"}:
        validate_final_review_units(units, contract, errors, workspace)
        validate_final_review_snapshot_chain(final, units, events, errors)


def final_review_passing_digest(final: object, workspace: Path) -> str | None:
    if not isinstance(final, dict) or not isinstance(final.get("attempts"), list):
        return None
    passing = [attempt for attempt in final["attempts"]
               if isinstance(attempt, dict) and attempt.get("status") == "pass"]
    if len(passing) != 1:
        return None
    errors: list[str] = []
    snapshot = validate_diff_snapshot(passing[0].get("diff_snapshot"), workspace, "final review snapshot", errors)
    return snapshot["diff_digest"] if snapshot is not None else None
