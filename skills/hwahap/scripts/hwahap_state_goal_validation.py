"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def validate_goal_link(value: object, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("goal_link must be an object")
        return
    current = value.get("current")
    history = value.get("history")
    validate_goal_observation(current, "goal_link.current", errors)
    if not isinstance(history, list):
        errors.append("goal_link.history must be a list")
        return
    bound_pair = None
    saw_get_goal = False
    saw_bound = False
    for index, entry in enumerate(history, 1):
        validate_goal_observation(entry, f"goal_link.history[{index}]", errors)
        if not isinstance(entry, dict):
            continue
        if entry.get("mode") != "bound":
            if saw_bound:
                errors.append("goal_link cannot downgrade after a bound receipt")
            continue
        saw_bound = True
        pair = (entry.get("thread_id"), entry.get("objective_sha256"))
        if bound_pair is None and entry.get("source") == "codex.get_goal":
            bound_pair = pair
            saw_get_goal = True
        elif bound_pair is None and entry.get("source") == "codex.update_goal":
            errors.append("goal_link update_goal receipt requires a prior get_goal binding")
        elif pair != bound_pair:
            errors.append("goal_link bound thread/objective must remain unchanged")
        if entry.get("source") == "codex.get_goal":
            saw_get_goal = True
        elif entry.get("source") == "codex.update_goal" and not saw_get_goal:
            errors.append("goal_link update_goal receipt requires a prior get_goal binding")
    if not history and isinstance(current, dict) and current.get("mode") != "unobserved":
        errors.append("goal_link.current must be unobserved when history is empty")
    if history and current != history[-1]:
        errors.append("goal_link.current must equal the last history entry")


def safe_relative_path(value: object) -> bool:
    if not required_text(value):
        return False
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        return False
    text = value.strip()
    if "\\" in text or Path(text).is_absolute() or text.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", text):
        return False
    return all(part not in ("", ".", "..") for part in re.split(r"[/\\]", text))


def paths_overlap(left: str, right: str) -> bool:
    left_prefix = left.rstrip("/") + "/"
    right_prefix = right.rstrip("/") + "/"
    return (left == right or left.startswith(right_prefix) or right.startswith(left_prefix)
            or fnmatch.fnmatch(left, right) or fnmatch.fnmatch(right, left))


def validate_failure(value: object, label: str, errors: list[str]) -> None:
    failure = value if isinstance(value, dict) else {}
    code = failure.get("code")
    if not isinstance(code, str) or code not in FAILURE_CODES or not required_text(failure.get("reason")):
        errors.append(f"{label}: invalid failure code or reason")
    evidence = failure.get("evidence")
    if (not isinstance(evidence, list) or not evidence or any(not required_text(item) for item in evidence)
            or not required_text(failure.get("recovery"))):
        errors.append(f"{label}: failure evidence and recovery are required")


def path_matches(path: str, allowed: object) -> bool:
    if not isinstance(allowed, list):
        return False
    for rule in allowed:
        if not isinstance(rule, str):
            continue
        prefix = rule.rstrip("/") + "/"
        if path == rule or path.startswith(prefix) or fnmatch.fnmatch(path, rule):
            return True
    return False
