"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def validate_review_history(unit: dict, contract: dict, errors: list[str], workspace: Path | None = None) -> list[str]:
    history = unit.get("review_history")
    label = str(unit.get("unit_id"))
    if not isinstance(history, list):
        errors.append(f"{label}: review_history must be a list")
        return []
    outcomes = _validate_review_rounds(history, unit, contract, errors, workspace)
    improvements = unit.get("improvement_history")
    if not isinstance(improvements, list):
        errors.append(f"{label}: improvement_history must be a list")
        improvements = []
    failures = [index for index, outcome in enumerate(outcomes, 1) if outcome == "fail"]
    failure_records: dict[int, dict] = {}
    pairs: set[tuple[object, object]] = set()
    for record in improvements:
        if not isinstance(record, dict):
            errors.append(f"{label}: improvement record must be an object")
            continue
        after_round = record.get("after_round")
        if not isinstance(after_round, int) or isinstance(after_round, bool) or after_round not in failures:
            errors.append(f"{label}: improvement record must follow a failed round")
            continue
        ordinal = failures.index(after_round) + 1
        kind = "terra_recovery" if ordinal == 1 else "sol_replan" if ordinal == 2 else "recursive_improvement"
        validate_improvement(record, after_round, kind, label, errors)
        if after_round in failure_records:
            errors.append(f"{label}: duplicate improvement round")
        failure_records[after_round] = record
        pair = (record.get("failure_signature"), record.get("strategy_digest"))
        if pair in pairs:
            errors.append(f"{label}: failure signature and strategy digest were reused")
        pairs.add(pair)
    status = unit.get("status")
    for after_round in failures:
        optional_terminal = status in {"blocked", "failed", "awaiting_user"} and after_round == failures[-1]
        pending_improvement = status == "reviewing" and after_round == failures[-1]
        if not optional_terminal and not pending_improvement and after_round not in failure_records:
            errors.append(f"{label}: failed round {after_round} requires improvement")
    replan_count = unit.get("replan_count", 0)
    if not isinstance(replan_count, int) or isinstance(replan_count, bool) or replan_count < 0:
        errors.append(f"{label}: replan_count must be a nonnegative integer")
        replan_count = 0
    expected_replans = sum(record.get("kind") in {"sol_replan", "recursive_improvement"} for record in failure_records.values())
    if replan_count != expected_replans:
        errors.append(f"{label}: replan_count does not match improvement history")
    if "pass" in outcomes:
        first_pass = outcomes.index("pass")
        if any(outcome == "fail" for outcome in outcomes[first_pass + 1:]):
            errors.append(f"{label}: failed review cannot follow a passing round")
    pending_improvement = (status == "reviewing" and outcomes and outcomes[-1] == "fail"
                           and failures[-1] not in failure_records)
    if status == "reviewing" and outcomes and outcomes[-1] == "fail" and not pending_improvement:
        errors.append(f"{label}: reviewing cannot end on a failed review")
    if status == "recovery" and (outcomes != ["fail"] or not failures or failures[0] != 1
                                  or 1 not in failure_records or failure_records[1].get("kind") != "terra_recovery"):
        errors.append(f"{label}: recovery requires first failed round terra_recovery")
    if status == "replan_required" and (len(failures) < 2 or not outcomes or outcomes[-1] != "fail"
                                         or failures[-1] not in failure_records):
        errors.append(f"{label}: replan_required requires two failed rounds and a corresponding later improvement")
    if status == "passed":
        if not outcomes or outcomes[-1] != "pass":
            errors.append(f"{label}: passed unit must end in a passing review")
        if any(failure not in failure_records for failure in failures):
            errors.append(f"{label}: passed unit requires improvement for every failed round")
    return outcomes


def has_pending_improvement(unit: dict) -> bool:
    if unit.get("status") != "reviewing":
        return False
    reviews = unit.get("review_history")
    improvements = unit.get("improvement_history")
    if not isinstance(reviews, list) or not isinstance(improvements, list) or not reviews:
        return False
    failures = [index for index, review in enumerate(reviews, 1)
                if isinstance(review, dict) and review.get("outcome") == "fail"]
    if not failures or not isinstance(reviews[-1], dict) or reviews[-1].get("outcome") != "fail":
        return False
    return not any(isinstance(record, dict) and record.get("after_round") == failures[-1]
                   for record in improvements)
