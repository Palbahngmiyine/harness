"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def validate_final_review(final: object, completed: bool, errors: list[str], workspace: Path) -> None:
    if not isinstance(final, dict):
        errors.append("final_review must be an object")
        return
    attempts = final.get("attempts")
    if not isinstance(attempts, list):
        errors.append("final_review.attempts must be a list")
        return
    status = final.get("status")
    if status not in {"pending", "pass", "fail"}:
        errors.append("final_review.status is invalid")
    if len(attempts) > 2:
        errors.append("final_review.attempts cannot contain more than two attempts")
    for index, attempt in enumerate(attempts, 1):
        if not isinstance(attempt, dict):
            errors.append(f"final_review.attempts[{index}] must be an object")
            continue
        if (set(attempt) != FINAL_REVIEW_ATTEMPT_FIELDS
                or attempt.get("model") != "gpt-5.6-sol" or attempt.get("effort") not in {"ultra", "xhigh"}
                or attempt.get("status") not in {"pass", "fail", "unavailable", "unsupported"}
                or not required_text(attempt.get("thread_id"))):
            errors.append(f"final_review.attempts[{index}] is incomplete")
        snapshot = validate_diff_snapshot(attempt.get("diff_snapshot"), workspace,
                                          f"final_review.attempts[{index}].diff_snapshot", errors)
        if snapshot is not None and attempt.get("diff_digest") != snapshot["diff_digest"]:
            errors.append(f"final_review.attempts[{index}].diff_digest does not match snapshot")
        evidence = attempt.get("evidence")
        if not isinstance(evidence, list) or not evidence or any(not required_text(item) for item in evidence):
            errors.append(f"final_review.attempts[{index}].evidence must be nonempty")
    valid = False
    if status == "pending":
        valid = len(attempts) == 0 or (
            len(attempts) == 1 and isinstance(attempts[0], dict)
            and attempts[0].get("effort") == "ultra"
            and attempts[0].get("status") in {"unavailable", "unsupported"}
        )
    elif status == "pass":
        valid = (
            len(attempts) == 1 and isinstance(attempts[0], dict)
            and attempts[0].get("effort") == "ultra" and attempts[0].get("status") == "pass"
        ) or (
            len(attempts) == 2 and all(isinstance(attempt, dict) for attempt in attempts)
            and attempts[0].get("effort") == "ultra"
            and attempts[0].get("status") in {"unavailable", "unsupported"}
            and attempts[1].get("effort") == "xhigh" and attempts[1].get("status") == "pass"
        )
    elif status == "fail":
        valid = (
            len(attempts) == 1 and isinstance(attempts[0], dict)
            and attempts[0].get("effort") == "ultra" and attempts[0].get("status") == "fail"
        ) or (
            len(attempts) == 2 and all(isinstance(attempt, dict) for attempt in attempts)
            and attempts[0].get("effort") == "ultra"
            and attempts[0].get("status") in {"unavailable", "unsupported"}
            and attempts[1].get("effort") == "xhigh"
            and attempts[1].get("status") in {"fail", "unavailable", "unsupported"}
        )
    if not valid:
        errors.append("final_review status and attempts do not match the allowed aggregate matrix")
        if completed:
            errors.append("completed final review attempts are invalid")
    if len(attempts) == 2 and all(isinstance(attempt, dict) for attempt in attempts):
        if attempts[0].get("diff_digest") != attempts[1].get("diff_digest"):
            errors.append("final review attempts must share diff digest")
        if attempts[0].get("diff_snapshot") != attempts[1].get("diff_snapshot"):
            errors.append("final review attempts must share diff snapshot")
    if completed and status != "pass":
        errors.append("completed final review must have aggregate pass")
