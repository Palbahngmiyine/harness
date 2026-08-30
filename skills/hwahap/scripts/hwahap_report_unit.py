"""Normalize report roles, reviews, units, and command receipts."""

import hashlib
from typing import Any

from hwahap_report_clean import pick, snapshot


def command_receipts(value: Any, prefix: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    return [{
        "name": f"{prefix}-{index}",
        "sha256": "sha256:" + hashlib.sha256(command.encode("utf-8")).hexdigest(),
    } for index, command in enumerate(value, 1) if isinstance(command, str)]


def roles(value: Any, workspace: str) -> dict[str, Any]:
    names = ("planner", "orchestrator", "implementer", "verifier",
             "scope_reviewer", "final_reviewer")
    keys = ("agent", "model", "effort", "fast", "fallback_effort")
    return {name: pick(value.get(name), keys, workspace) for name in names
            if isinstance(value, dict) and isinstance(value.get(name), dict)}


def review(value: Any, workspace: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result = pick(value, ("round", "diff_digest", "changed_paths", "outcome"),
                  workspace)
    top_snapshot = snapshot(value.get("diff_snapshot"), workspace)
    if top_snapshot:
        result["diff_snapshot"] = top_snapshot
    for key in ("verifier", "scope_reviewer"):
        reviewer = value.get(key)
        result[key] = pick(reviewer, ("model", "effort", "status", "thread_id",
            "diff_digest", "evidence"), workspace)
        reviewer_snapshot = snapshot(
            reviewer.get("diff_snapshot") if isinstance(reviewer, dict) else None,
            workspace)
        if reviewer_snapshot:
            result[key]["diff_snapshot"] = reviewer_snapshot
    return result


def unit(value: Any, workspace: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    result = pick(value, ("unit_id", "title", "status", "writer", "allowed_paths",
                          "replan_count"), workspace)
    result["acceptance_commands"] = command_receipts(
        value.get("acceptance_commands"), "acceptance-command")
    receipt_keys = ("test_id", "command_index", "command_sha256", "source",
        "execution_receipt_sha256", "observer_role", "observer_thread_id",
        "diff_digest", "started_at", "ended_at", "exit_code", "output_sha256",
        "status")
    result["test_receipts"] = []
    for item in value.get("test_receipts", []):
        if not isinstance(item, dict):
            continue
        receipt = pick(item, receipt_keys, workspace)
        receipt_snapshot = snapshot(item.get("diff_snapshot"), workspace)
        if receipt_snapshot:
            receipt["diff_snapshot"] = receipt_snapshot
        result["test_receipts"].append(receipt)
    result["review_history"] = [review(item, workspace)
        for item in value.get("review_history", [])]
    improve_keys = ("after_round", "kind", "failure_signature", "root_cause",
        "hypothesis", "action", "strategy_digest", "scope_status", "evidence")
    result["improvement_history"] = [pick(item, improve_keys, workspace)
        for item in value.get("improvement_history", [])]
    for key in ("failure", "recovery"):
        result[key] = pick(value.get(key),
            ("code", "reason", "evidence", "recovery", "action"), workspace)
    return result
