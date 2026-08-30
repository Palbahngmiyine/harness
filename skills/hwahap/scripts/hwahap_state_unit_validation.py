"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def validate_unit(unit: dict, contract: dict, seen: set[str], errors: list[str], workspace: Path | None = None) -> list[str]:
    unit_id = unit.get("unit_id")
    if not isinstance(unit_id, str) or not SLUG.fullmatch(unit_id):
        errors.append("unit_id must be a safe nonempty slug and unique")
    elif unit_id in seen:
        errors.append("unit_id must be nonempty and unique")
    else:
        seen.add(unit_id)
    status = unit.get("status")
    if not isinstance(status, str) or status not in UNIT_STATES:
        errors.append(f"{unit_id}: invalid status")
    if unit.get("writer") != "hwahap-luna-implementer":
        errors.append(f"{unit_id}: invalid writer")
    if not required_text(unit.get("title")):
        errors.append(f"{unit_id}: title must be a nonempty observable-change description")
    for field in ("allowed_paths", "acceptance_commands"):
        if not isinstance(unit.get(field), list) or not unit[field]:
            errors.append(f"{unit_id}: {field} must be nonempty")
    commands = unit.get("acceptance_commands")
    if isinstance(commands, list) and any(not safe_test_command(command) for command in commands):
        errors.append("credential-bearing test command is unsafe")
    if "reviews" in unit and not isinstance(unit.get("reviews"), dict):
        errors.append(f"{unit_id}: reviews must be an object")
    if contract.get("locked") and isinstance(contract.get("allowed_paths"), list) and isinstance(unit.get("allowed_paths"), list):
        if any(not isinstance(path, str) or path not in contract["allowed_paths"] for path in unit["allowed_paths"]):
            errors.append(f"{unit_id}: allowed_paths must be exact locked-contract members")
    if contract.get("locked") and isinstance(contract.get("test_commands"), list) and isinstance(unit.get("acceptance_commands"), list):
        if any(not isinstance(command, str) or command not in contract["test_commands"] for command in unit["acceptance_commands"]):
            errors.append(f"{unit_id}: acceptance_commands must be exact locked-contract members")
    latest_receipts = validate_test_receipts(unit, errors, workspace)
    if isinstance(status, str) and status in FAILURE_STATES:
        validate_failure(unit.get("failure"), str(unit_id), errors)
    outcomes = validate_review_history(unit, contract, errors, workspace) if isinstance(status, str) else []
    history = unit.get("review_history")
    if status == "planned" and history != []:
        errors.append(f"{unit_id}: planned unit must have empty review_history")
    elif status == "implementing" and isinstance(history, list) and history:
        if not outcomes or outcomes[-1] != "fail":
            errors.append(f"{unit_id}: implementing unit history must end in a failed review")
    if status == "passed" and isinstance(history, list) and history and outcomes and outcomes[-1] == "pass":
        review = history[-1]
        verifier = review.get("verifier") if isinstance(review, dict) else None
        if isinstance(verifier, dict):
            for receipt in latest_receipts.values():
                if receipt.get("observer_thread_id") != verifier.get("thread_id"):
                    errors.append(f"{unit_id}: passing test receipt observer does not match review verifier")
                if receipt.get("diff_digest") != review.get("diff_digest"):
                    errors.append(f"{unit_id}: passing test receipt diff does not match review")
                if receipt.get("diff_snapshot") != review.get("diff_snapshot"):
                    errors.append(f"{unit_id}: passing test receipt snapshot does not match review")
    return outcomes


def validate_records(value: object, fields: tuple[str, ...], label: str, errors: list[str]) -> int:
    if not isinstance(value, list):
        errors.append(f"{label} must be a list")
        return 0
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict):
            errors.append(f"{label}[{index}] must be an object")
            continue
        if any(not required_text(item.get(field)) for field in fields):
            errors.append(f"{label}[{index}] is incomplete")
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence or any(not required_text(ref) for ref in evidence):
            errors.append(f"{label}[{index}].evidence must be nonempty")
    return len(value)
