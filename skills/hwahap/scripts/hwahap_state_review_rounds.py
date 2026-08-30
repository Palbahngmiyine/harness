"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def validate_improvement(record: object, after_round: int, kind: str, label: str, errors: list[str]) -> bool:
    if not isinstance(record, dict):
        errors.append(f"{label}: improvement record must be an object")
        return False
    if record.get("after_round") != after_round or record.get("kind") != kind:
        errors.append(f"{label}: improvement record round or kind is invalid")
    for field in ("failure_signature", "strategy_digest"):
        if not isinstance(record.get(field), str) or not SHA256.fullmatch(record[field]):
            errors.append(f"{label}: improvement {field} is invalid")
    if any(not required_text(record.get(field)) for field in ("root_cause", "hypothesis", "action")):
        errors.append(f"{label}: improvement explanation is incomplete")
    if record.get("scope_status") != "within_contract":
        errors.append(f"{label}: improvement scope is invalid")
    evidence = record.get("evidence")
    if not isinstance(evidence, list) or not evidence or any(not required_text(item) for item in evidence):
        errors.append(f"{label}: improvement evidence is required")
    return True


def _validate_review_rounds(history: list, unit: dict, contract: dict,
                            errors: list[str], workspace: Path | None) -> list[str]:
    label = str(unit.get("unit_id"))
    outcomes: list[str] = []
    for index, review in enumerate(history, 1):
        if not isinstance(review, dict):
            errors.append(f"{label}: review round {index} must be an object")
            continue
        if review.get("round") != index:
            errors.append(f"{label}: review rounds must be contiguous")
        digest = review.get("diff_digest")
        snapshot = validate_diff_snapshot(review.get("diff_snapshot"), workspace,
                                          f"{label}: review round {index} diff_snapshot", errors)
        if snapshot is not None and (digest != snapshot["diff_digest"] or review.get("changed_paths") != snapshot["changed_paths"]):
            errors.append(f"{label}: review round {index} diff fields do not match snapshot")
        changed_paths = snapshot["changed_paths"] if snapshot is not None else review.get("changed_paths")
        if isinstance(changed_paths, list) and changed_paths:
            for path in changed_paths:
                if not path_matches(path, unit.get("allowed_paths", [])):
                    errors.append(f"{label}: changed path is outside unit scope: {path}")
                forbidden = contract.get("forbidden_changes")
                if isinstance(forbidden, list) and any(
                        isinstance(item, str) and paths_overlap(path, item) for item in forbidden):
                    errors.append(f"{label}: changed path overlaps forbidden_changes: {path}")
        else:
            errors.append(f"{label}: changed_paths is invalid")
        statuses = []
        thread_ids = []
        for key, model in (("verifier", "gpt-5.6-luna"), ("scope_reviewer", "gpt-5.6-terra")):
            reviewer = review.get(key)
            if not isinstance(reviewer, dict):
                errors.append(f"{label}: {key} review must be an object")
                reviewer = {}
            if reviewer.get("model") != model or reviewer.get("effort") != "xhigh":
                errors.append(f"{label}: {key} model or effort is invalid")
            status = reviewer.get("status")
            if not isinstance(status, str) or status not in {"pass", "fail"}:
                errors.append(f"{label}: {key} status is invalid")
            statuses.append(status)
            thread_id = reviewer.get("thread_id")
            if not required_text(thread_id):
                errors.append(f"{label}: {key} thread_id is required")
            thread_ids.append(thread_id)
            if reviewer.get("diff_digest") != digest or not isinstance(reviewer.get("diff_digest"), str):
                errors.append(f"{label}: {key} diff digest does not match")
            evidence = reviewer.get("evidence")
            if not isinstance(evidence, list) or not evidence or any(not required_text(item) for item in evidence):
                errors.append(f"{label}: {key} evidence is required")
        if len(thread_ids) == 2 and required_text(thread_ids[0]) and thread_ids[0] == thread_ids[1]:
            errors.append(f"{label}: review thread IDs must be distinct")
        outcome = review.get("outcome")
        expected = "pass" if statuses == ["pass", "pass"] else "fail"
        if outcome != expected:
            errors.append(f"{label}: review outcome does not match reviewer statuses")
        outcomes.append(outcome if isinstance(outcome, str) and outcome in {"pass", "fail"} else expected)
    return outcomes
