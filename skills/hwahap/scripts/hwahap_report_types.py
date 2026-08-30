"""Shared report schema constants."""

import re


class HwahapReportError(ValueError):
    """Stable direct-report validation error."""


EVENT_FIELDS = (
    "timestamp", "type", "sequence", "entity", "from", "to", "actor",
    "role", "reason", "input_digest", "evidence_refs", "review_round",
)
CONTRACT_LISTS = (
    "goals", "non_goals", "allowed_paths", "forbidden_changes",
    "acceptance_criteria", "test_commands",
)
REPORT_IDS = (
    "summary", "report-data", "contract", "agents", "units", "timeline",
    "reviews", "scope-audit", "tests-metrics", "failures-recovery",
    "deviations", "provenance", "improvement-candidates", "next-actions",
)
DIFF_SNAPSHOT_FIELDS = (
    "base_commit", "target_commit", "base_tree", "target_tree",
    "diff_digest", "changed_paths",
)
IMPROVEMENT_CANDIDATE_FIELDS = (
    "status", "summary", "evidence", "expected_effect", "next_action",
)
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
ABS_PATH = re.compile(r"(?<![A-Za-z0-9_])/(?:[^\s<>\"']+/)+[^\s<>\"']+")
