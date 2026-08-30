"""Normalize Goal provenance and improvement candidates."""

from typing import Any

from hwahap_report_clean import pick
from hwahap_report_types import IMPROVEMENT_CANDIDATE_FIELDS

GOAL_KEYS = (
    "mode", "source", "thread_id", "external_status", "objective_sha256",
    "receipt_sha256", "reason", "evidence", "observed_at", "completion_sync",
    "sync_result", "token_total",
)


def goal_link(value: Any, workspace: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"current": {}, "history": []}
    history = value.get("history") if isinstance(value.get("history"), list) else []
    return {
        "current": pick(value.get("current"), GOAL_KEYS, workspace),
        "history": [pick(item, GOAL_KEYS, workspace) for item in history],
    }


def improvement_candidates(value: Any, workspace: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [pick(item, IMPROVEMENT_CANDIDATE_FIELDS, workspace)
            for item in value if isinstance(item, dict)]
