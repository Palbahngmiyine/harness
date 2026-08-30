"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())


def required_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


ROLE_MAP = {
    "planner": {"agent": "hwahap-sol-planner", "model": "gpt-5.6-sol", "effort": "xhigh"},
    "orchestrator": {"agent": "hwahap-sol-orchestrator", "model": "gpt-5.6-sol", "effort": "xhigh", "fast": "best_effort"},
    "implementer": {"agent": "hwahap-luna-implementer", "model": "gpt-5.6-luna", "effort": "high"},
    "verifier": {"agent": "hwahap-luna-verifier", "model": "gpt-5.6-luna", "effort": "xhigh"},
    "scope_reviewer": {"agent": "hwahap-terra-scope-reviewer", "model": "gpt-5.6-terra", "effort": "xhigh"},
    "final_reviewer": {"agent": "hwahap-sol-final-reviewer", "model": "gpt-5.6-sol", "effort": "ultra", "fallback_effort": "xhigh"},
}
CONTRACT_LISTS = (
    "goals", "non_goals", "allowed_paths", "forbidden_changes",
    "acceptance_criteria", "test_commands",
)
CANDIDATE_FIELDS = frozenset(("status", "summary", "evidence", "expected_effect", "next_action"))
EVENT_FIELDS = (
    "timestamp", "type", "sequence", "entity", "from", "to", "actor", "role",
    "reason", "input_digest", "evidence_refs", "review_round",
)
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
DIFF_SNAPSHOT_FIELDS = frozenset(("base_commit", "target_commit", "base_tree", "target_tree", "diff_digest", "changed_paths"))
FINAL_REVIEW_ATTEMPT_FIELDS = frozenset(("model", "effort", "status", "thread_id", "evidence", "diff_digest", "diff_snapshot"))
COMMAND_CREDENTIAL = re.compile(r"(?ix)(?:\b(?:token|aws_session_token|aws_secret_access_key|aws_access_key_id|github_token|openai_api_key)\s*[:=]\s*\S+|--(?:token|session-token|password|secret|api[_-]?key|private[_-]?key)(?:=|\s+)\S+|\b(?:cookie|set-cookie|authorization|bearer|password|secret|api[_ -]?key|private[_ -]?key)\b\s*[:=]?\s*\S+|https?://[^/\s:@]+:[^/\s@]+@[^\s]+|-----BEGIN [^-]+-----)")
ASSIGNMENT_TOKEN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SHELL_CONTROL = re.compile(r"[;|&<>`\x00\r\n]")
SHELL_WRAPPERS = frozenset(("sh", "bash", "zsh", "dash", "ksh", "fish"))
