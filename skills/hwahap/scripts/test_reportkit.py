"""Shared fixture and imports for report test slices."""
from __future__ import annotations
import copy
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("hwahap_report.py")
def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
report = _load("hwahap_report", MODULE_PATH)
state = _load("hwahap_state_for_report", MODULE_PATH.with_name("hwahap_state.py"))

def _relative_luminance(value: str) -> float:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    channels = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

def _contrast(first: str, second: str) -> float:
    lighter, darker = sorted((_relative_luminance(first), _relative_luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)

class _ReviewTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.rows.append([])
        elif tag in {"th", "td"} and self.rows:
            self.rows[-1].append((tag, dict(attrs).get("colspan")))

class HwahapReportTests(unittest.TestCase):
    def fixture(self):
        contract = {field: ["src"] for field in report.CONTRACT_LISTS}
        contract.update({"schema_version": 1, "goal_id": "g", "goal": "<script>alert(1)</script>", "locked": True, "lock_sha256": "sha256:" + "a" * 64, "spec": {"source": "/tmp/work/spec.md", "sha256": "b" * 64, "confirmed_at": "now"}, "unknown": "do not include"})
        run = {"schema_version": 1, "goal_id": "g", "status": "completed", "started_at": "now", "completed_at": "later", "roles": {"orchestrator": {"agent": "sol", "model": "gpt-5.6-sol", "effort": "xhigh", "fast": "Fast"}}, "agent_profiles": {"sol.toml": "sha256:" + "c" * 64}, "fast_status": "unknown", "metrics": {"unit_count": 1, "agent_runs": {"availability": "unavailable", "reason": "platform aggregate not exposed", "source": None, "total": None}, "review_rounds": 1, "test_runs": 1, "token_usage": {"availability": "unavailable", "reason": "hidden", "total": None}}, "deviations": [], "deferred_security": [], "final_review": {"status": "pass", "attempts": [{"model": "gpt-5.6-sol", "effort": "ultra", "status": "pass", "thread_id": "final", "evidence": ["review"]}]}, "goal_link": {"current": {"mode": "unobserved"}, "history": []}, "raw_log": "secret"}
        unit = {"unit_id": "u", "title": "unit", "status": "passed", "allowed_paths": ["/tmp/work/src"], "acceptance_commands": ["pytest"], "review_history": [], "improvement_history": [], "failure": {}, "recovery": {}, "prompt": "ignore this"}
        event = {field: (1 if field == "sequence" else 0 if field == "review_round" else ["ev"] if field == "evidence_refs" else "value") for field in report.EVENT_FIELDS}
        return contract, run, [unit], [event], {"contract": "sha256:" + "d" * 64}

__all__ = [name for name in globals() if not name.startswith("__") and name != "load_tests"]
