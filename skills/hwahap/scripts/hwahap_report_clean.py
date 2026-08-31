"""Allowlist and normalize report input values."""

from typing import Any

from hwahap_report_security import text
from hwahap_report_types import DECISION_CONTEXT_FIELDS, DIFF_SNAPSHOT_FIELDS


def clean(value: Any, workspace: str = "") -> Any:
    if isinstance(value, str):
        return text(value, workspace)
    if isinstance(value, list):
        return [clean(item, workspace) for item in value]
    if isinstance(value, dict):
        ordered = sorted(value.items(), key=lambda pair: str(pair[0]))
        return {str(key): clean(item, workspace) for key, item in ordered}
    return value


def pick(value: Any, keys: tuple[str, ...], workspace: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result = {}
    for key in keys:
        if key in value or key == "decision_context":
            result[key] = (decision_context(value.get(key), workspace)
                           if key == "decision_context" else clean(value[key], workspace))
    return result


def decision_context(value: Any, workspace: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {key: clean(value[key], workspace) for key in DECISION_CONTEXT_FIELDS
            if key in value}


def snapshot(value: Any, workspace: str) -> dict[str, Any]:
    return pick(value, DIFF_SNAPSHOT_FIELDS, workspace)


def _audit_path(item: dict, workspace: str) -> dict:
    result = {
        "path": clean(item["path"], workspace),
        "contract_allowed": bool(item.get("contract_allowed")),
        "passed_unit_covered": bool(item.get("passed_unit_covered")),
        "forbidden_overlap": bool(item.get("forbidden_overlap")),
        "matched_contract_rules": clean([
            rule for rule in item.get("matched_contract_rules", [])
            if isinstance(rule, str)], workspace),
        "matched_forbidden_rules": clean([
            rule for rule in item.get("matched_forbidden_rules", [])
            if isinstance(rule, str)], workspace),
        "verdict": item.get("verdict") if item.get("verdict") in {"pass", "fail"}
        else "fail",
    }
    result["covering_passed_units"] = [{
        "unit_id": clean(unit.get("unit_id"), workspace),
        "matched_rules": clean(unit.get("matched_rules", []), workspace),
    } for unit in item.get("covering_passed_units", []) if isinstance(unit, dict)]
    evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
    result["evidence"] = {
        "diff_digest": evidence.get("diff_digest"),
        "contract_lock_sha256": evidence.get("contract_lock_sha256"),
        "passed_unit_ids": [unit_id for unit_id in evidence.get("passed_unit_ids", [])
                            if isinstance(unit_id, str)],
    }
    return result


def scope_audit(value: Any, workspace: str) -> dict[str, Any]:
    value = value if isinstance(value, dict) else {}
    result = {
        "authority": "derived-report-only", "affects_gate": False,
        "source_diff_digest": value.get("source_diff_digest"),
        "contract_lock_sha256": value.get("contract_lock_sha256"), "paths": [],
    }
    for key in ("source_diff_digest", "contract_lock_sha256"):
        if not isinstance(result[key], str):
            result[key] = None
    values = value.get("paths", []) if isinstance(value.get("paths"), list) else []
    result["paths"] = [_audit_path(item, workspace) for item in values
                       if isinstance(item, dict) and isinstance(item.get("path"), str)]
    return result
