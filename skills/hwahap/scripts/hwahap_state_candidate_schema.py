"""Validate report-only improvement candidate records."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())


def validate_improvement_candidate(
        record: object, label: str, errors: list[str]) -> None:
    if not isinstance(record, dict):
        errors.append(f"{label} must be an object")
        return
    if set(record) != CANDIDATE_FIELDS:
        errors.append(f"{label} has invalid fields")
    if record.get("status") != "proposed":
        errors.append(f"{label}.status must be proposed")
    fields = ("summary", "expected_effect", "next_action")
    if any(not required_text(record.get(field)) for field in fields):
        errors.append(
            f"{label} requires summary, expected_effect, and next_action")
    evidence = record.get("evidence")
    if (not isinstance(evidence, list) or not evidence
            or any(not required_text(item) for item in evidence)):
        errors.append(f"{label}.evidence must be nonempty")


def validate_improvement_candidates(value: object, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append("improvement_candidates must be a list")
        return
    for index, record in enumerate(value, 1):
        validate_improvement_candidate(
            record, f"improvement_candidates[{index}]", errors)
