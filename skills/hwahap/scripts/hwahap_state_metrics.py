"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def validate_metrics(run: dict, units: list[dict], histories: list[list[str]], deviations: list[object], errors: list[str]) -> None:
    metrics = run.get("metrics")
    if not isinstance(metrics, dict):
        errors.append("metrics must be an object")
        return
    counters = ("unit_count", "review_rounds", "recoveries", "replans", "scope_deviations", "test_runs", "elapsed_seconds")
    for field in counters:
        value = metrics.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            errors.append(f"metrics.{field} must be a nonnegative integer")
    agent_runs = metrics.get("agent_runs")
    expected_agent_receipt = {"availability": "unavailable", "reason": "platform aggregate not exposed", "source": None, "total": None}
    if agent_runs != expected_agent_receipt:
        errors.append("metrics.agent_runs must be an unavailable platform receipt")
    token_usage = metrics.get("token_usage")
    if not isinstance(token_usage, dict):
        errors.append("metrics.token_usage must be an object")
    else:
        availability = token_usage.get("availability")
        total = token_usage.get("total")
        if not isinstance(availability, str) or availability not in {"available", "unavailable"}:
            errors.append("token_usage availability is invalid")
        elif availability == "available":
            source = token_usage.get("source")
            if (not isinstance(total, int) or isinstance(total, bool) or total < 0
                    or source not in {"codex.get_goal", "codex.update_goal"} or token_usage.get("reason") is not None):
                errors.append("available token_usage requires validated Goal receipt, total, and source")
            else:
                goal_link = run.get("goal_link") if isinstance(run.get("goal_link"), dict) else {}
                history = goal_link.get("history") if isinstance(goal_link.get("history"), list) else []
                receipts = [entry for entry in history if isinstance(entry, dict)
                            and entry.get("source") == source and isinstance(entry.get("receipt_sha256"), str)
                            and SHA256.fullmatch(entry["receipt_sha256"])
                            and entry.get("token_total") == total]
                if not receipts:
                    errors.append("available token_usage requires a matching Goal receipt")
        elif availability == "unavailable" and (token_usage.get("source") is not None or total is not None
                                                 or not required_text(token_usage.get("reason"))):
            errors.append("unavailable token_usage requires null source, null total, and reason")
    fast_status = run.get("fast_status")
    if fast_status != "unknown":
        errors.append("fast_status is invalid")
    if run.get("status") == "completed":
        expected = {
            "unit_count": len(units),
            "review_rounds": sum(len(history) for history in histories),
            "recoveries": sum(bool(history and history[0] == "fail") for history in histories),
            "replans": sum(sum(record.get("kind") in {"sol_replan", "recursive_improvement"}
                                for record in unit.get("improvement_history", []) if isinstance(record, dict))
                            for unit in units if isinstance(unit.get("improvement_history"), list)),
            "scope_deviations": len(deviations),
            "test_runs": sum(len(unit.get("test_receipts", [])) for unit in units if isinstance(unit.get("test_receipts"), list)),
        }
        for field, value in expected.items():
            if metrics.get(field) != value:
                errors.append(f"metrics.{field} is inconsistent")
