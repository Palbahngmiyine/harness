"""Validate the minimal S/A/U projection accepted by Hwahap."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())


def align_review_outputs(contract: dict, ids: tuple[set[str], set[str], set[str]]) -> None:
    ambiguity = contract["reviews"]["ambiguity_auditor"].get("output")
    ambiguity_keys = {"new_material_choices", "counterexamples", "contradictions",
        "invalid_forced_consequences", "invalid_local_coding", "unexamined_surfaces"}
    if not isinstance(ambiguity, dict) or set(ambiguity) != ambiguity_keys \
            or any(value != [] for value in ambiguity.values()):
        raise ValueError
    cold = contract["reviews"]["cold_consumer"].get("output")
    empty = {"required_user_choices", "implicit_assumptions", "contradictions",
             "underspecified_clauses", "unmapped_spec_ids", "local_choices"}
    if not isinstance(cold, dict) or set(cold) != empty | {"steps"} \
            or any(cold.get(key) != [] for key in empty) \
            or not isinstance(cold.get("steps"), list) or not cold["steps"]:
        raise ValueError
    covered = [set(), set(), set()]
    for step in cold["steps"]:
        if not isinstance(step, dict):
            raise ValueError
        refs = (step.get("spec_ids"), step.get("acceptance_ids"), step.get("unit_ids"))
        if any(not isinstance(value, list) for value in refs) \
                or any(not set(value) <= known for value, known in zip(refs, ids)):
            raise ValueError
        for found, value in zip(covered, refs):
            found.update(value)
    if tuple(covered) != ids:
        raise ValueError


def align_ids(items: object) -> set[str]:
    if not isinstance(items, list) or not items:
        raise ValueError
    values = [item.get("id") for item in items if isinstance(item, dict)]
    if len(values) != len(items) or any(not isinstance(item, str) or not item for item in values) \
            or len(values) != len(set(values)):
        raise ValueError
    return set(values)


def align_goal_trace(contract: dict, digest: str) -> dict:
    specs, checks, units = (contract.get("specifications"),
                            contract.get("acceptance_checks"),
                            contract.get("implementation_units"))
    spec_ids, check_ids, unit_ids = align_ids(specs), align_ids(checks), align_ids(units)
    align_review_outputs(contract, (spec_ids, check_ids, unit_ids))
    covered_specs, covered_checks = set(), set()
    for check in checks:
        refs = check.get("spec_ids")
        if not isinstance(refs, list) or not refs or not set(refs) <= spec_ids:
            raise ValueError
        covered_specs.update(refs)
    for unit in units:
        srefs, arefs = unit.get("spec_ids"), unit.get("acceptance_ids")
        if not isinstance(srefs, list) or not srefs or not set(srefs) <= spec_ids \
                or not isinstance(arefs, list) or not arefs or not set(arefs) <= check_ids:
            raise ValueError
        covered_specs.update(srefs); covered_checks.update(arefs)
    choices = contract.get("choices")
    if not isinstance(choices, list) or any(not isinstance(item, dict)
            or item.get("status") not in {"confirmed", "superseded"} for item in choices) \
            or covered_specs != spec_ids or covered_checks != check_ids \
            or any(not isinstance(item, dict) or item.get("status") == "open"
                   for item in contract.get("open_items", [])):
        raise ValueError
    return {"schema": "align-goal/v1", "revision": contract["revision"],
            "spec_digest": digest, "specifications": specs,
            "acceptance_checks": checks, "implementation_units": units}
