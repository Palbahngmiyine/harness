"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def validate_final_review_snapshot_scope(final: object, contract: dict,
                                         units: list[dict], errors: list[str]) -> None:
    """Close final-review snapshots against both locked and passed-unit scope."""
    if not isinstance(final, dict) or not isinstance(final.get("attempts"), list):
        return
    for attempt in final["attempts"]:
        if not isinstance(attempt, dict):
            continue
        snapshot = attempt.get("diff_snapshot")
        changed_paths = snapshot.get("changed_paths") if isinstance(snapshot, dict) else None
        if not isinstance(changed_paths, list) or not changed_paths:
            continue
        for path in changed_paths:
            if not isinstance(path, str):
                continue
            audit = evaluate_final_review_snapshot_path(path, contract, units)
            if not audit["contract_allowed"]:
                errors.append("final review snapshot path is outside locked contract scope")
            if not audit["passed_unit_covered"]:
                errors.append("final review snapshot path is outside passed-unit scope")
            if audit["forbidden_overlap"]:
                errors.append("final review snapshot path overlaps forbidden_changes")


def evaluate_final_review_snapshot_path(path: str, contract: dict, units: list[dict]) -> dict:
    contract_rules = contract.get("allowed_paths") if isinstance(contract, dict) else []
    contract_rules = [rule for rule in contract_rules if isinstance(rule, str)] if isinstance(contract_rules, list) else []
    matched_contract = [rule for rule in contract_rules if path_matches(path, [rule])]
    covering = []
    for unit in units:
        if not isinstance(unit, dict) or unit.get("status") != "passed":
            continue
        rules = unit.get("allowed_paths")
        rules = [rule for rule in rules if isinstance(rule, str) and safe_relative_path(rule)] if isinstance(rules, list) else []
        matched = [rule for rule in rules if path_matches(path, [rule])]
        if matched:
            covering.append({"unit_id": unit.get("unit_id"), "matched_rules": matched})
    forbidden = contract.get("forbidden_changes") if isinstance(contract, dict) else []
    matched_forbidden = [rule for rule in forbidden if isinstance(rule, str) and paths_overlap(path, rule)] if isinstance(forbidden, list) else []
    return {"contract_allowed": bool(matched_contract), "passed_unit_covered": bool(covering),
            "forbidden_overlap": bool(matched_forbidden), "matched_contract_rules": matched_contract,
            "covering_passed_units": covering, "matched_forbidden_rules": matched_forbidden,
            "verdict": "pass" if matched_contract and covering and not matched_forbidden else "fail"}


def build_scope_audit(run: dict, contract: dict, units: list[dict]) -> dict:
    audit = {"authority": "derived-report-only", "affects_gate": False,
             "source_diff_digest": None, "contract_lock_sha256": contract.get("lock_sha256"), "paths": []}
    final = run.get("final_review") if isinstance(run, dict) else None
    attempts = final.get("attempts") if isinstance(final, dict) else None
    passing = [item for item in attempts if isinstance(item, dict) and item.get("status") == "pass"] if isinstance(attempts, list) else []
    if len(passing) != 1 or not isinstance(passing[0].get("diff_snapshot"), dict):
        return audit
    snapshot = passing[0]["diff_snapshot"]
    paths = snapshot.get("changed_paths")
    if not isinstance(paths, list):
        return audit
    audit["source_diff_digest"] = snapshot.get("diff_digest")
    seen: set[str] = set()
    for path in paths:
        if not isinstance(path, str) or path in seen:
            continue
        seen.add(path)
        result = evaluate_final_review_snapshot_path(path, contract, units)
        result["path"] = path
        result["evidence"] = {"diff_digest": snapshot.get("diff_digest"),
                               "contract_lock_sha256": contract.get("lock_sha256"),
                               "passed_unit_ids": [item.get("unit_id") for item in result["covering_passed_units"]]}
        audit["paths"].append(result)
    return audit


def final_review_failure_code(final: object) -> str | None:
    if (not isinstance(final, dict) or final.get("status") != "fail"
            or not isinstance(final.get("attempts"), list)):
        return None
    attempts = final["attempts"]
    if not attempts or not isinstance(attempts[-1], dict):
        return None
    return {"fail": "HW_FINAL_REVIEW_FAILED", "unavailable": "HW_MODEL_UNAVAILABLE",
            "unsupported": "HW_MODEL_UNAVAILABLE"}.get(attempts[-1].get("status"))
