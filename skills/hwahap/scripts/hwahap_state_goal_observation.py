"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def validate_goal_observation(value: object, label: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return
    mode = value.get("mode")
    if mode not in GOAL_MODES:
        errors.append(f"{label}.mode is invalid")
        return
    sync_result = value.get("sync_result")
    if "sync_result" not in value:
        errors.append(f"{label}.sync_result is required")
    if "token_total" not in value:
        errors.append(f"{label}.token_total is required")
    if mode != "bound" and sync_result is not None:
        errors.append(f"{label}.sync_result must be null for non-bound receipts")
    if not required_text(value.get("observed_at")) or not required_text(value.get("reason")):
        errors.append(f"{label} requires observed_at and reason")
    evidence = value.get("evidence")
    if not isinstance(evidence, list) or not evidence or any(not required_text(ref) for ref in evidence):
        errors.append(f"{label}.evidence must be nonempty")
    if mode == "bound":
        if value.get("source") not in {"codex.get_goal", "codex.update_goal"} or not required_text(value.get("thread_id")):
            errors.append(f"{label} bound source or thread_id is invalid")
        source = value.get("source")
        if source == "codex.get_goal":
            if value.get("external_status") != "active" or value.get("completion_sync") != "pending":
                errors.append(f"{label} active Goal receipt is invalid")
            if sync_result is not None:
                errors.append(f"{label}.sync_result must be null for get_goal receipts")
            if value.get("token_total") is not None and (not isinstance(value.get("token_total"), int) or isinstance(value.get("token_total"), bool) or value.get("token_total") < 0):
                errors.append(f"{label}.token_total is invalid")
        elif source == "codex.update_goal":
            if sync_result not in {"completed", "already_completed", "failed"}:
                errors.append(f"{label}.sync_result is invalid")
            expected = (("completed", "completed") if sync_result in {"completed", "already_completed"}
                        else ("active", "failed") if sync_result == "failed" else (None, None))
            if (value.get("external_status"), value.get("completion_sync")) != expected:
                errors.append(f"{label} completion Goal receipt is invalid")
            if sync_result in {"completed", "already_completed"} and (not isinstance(value.get("token_total"), int) or isinstance(value.get("token_total"), bool) or value.get("token_total") < 0):
                errors.append(f"{label}.token_total is required for successful completion")
            if sync_result == "failed" and value.get("token_total") is not None:
                errors.append(f"{label}.token_total must be null for failed completion")
        else:
            errors.append(f"{label} bound source is invalid")
        for field in ("objective_sha256", "receipt_sha256"):
            if not isinstance(value.get(field), str) or not SHA256.fullmatch(value[field]):
                errors.append(f"{label}.{field} is invalid")
    elif mode == "unobserved":
        if any(value.get(field) is not None for field in ("source", "thread_id", "objective_sha256", "receipt_sha256")):
            errors.append(f"{label} unobserved receipt fields must be null")
        if value.get("external_status") != "unknown" or value.get("completion_sync") != "pending" or value.get("token_total") is not None:
            errors.append(f"{label} unobserved status or completion_sync is invalid")
    else:
        if value.get("source") != "codex.get_goal" or value.get("thread_id") is not None:
            errors.append(f"{label} unbound source or thread_id is invalid")
        if value.get("external_status") != "unknown" or value.get("objective_sha256") is not None:
            errors.append(f"{label} unbound status or objective is invalid")
        receipt = value.get("receipt_sha256")
        if mode == "unavailable":
            if receipt is not None:
                errors.append(f"{label} unavailable receipt must be null")
        elif not isinstance(receipt, str) or not SHA256.fullmatch(receipt):
            errors.append(f"{label}.receipt_sha256 is invalid")
        if value.get("completion_sync") != "not_applicable" or value.get("token_total") is not None:
            errors.append(f"{label} unbound completion_sync must be not_applicable")
