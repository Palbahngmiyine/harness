"""Exact v4 schema for causal deviation records."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())

def validate_deviations(value: object, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append("deviations must be a list")
        return
    for index, item in enumerate(value, 1):
        label = f"deviations[{index}]"
        if not isinstance(item, dict) or set(item) != DEVIATION_FIELDS:
            errors.append(f"{label} is incomplete; must be an exact v4 deviation")
            continue
        if any(not required_text(item.get(field)) for field in DEVIATION_TEXT_FIELDS):
            errors.append(f"{label} has empty causal fields")
        evidence = item.get("evidence")
        if (not isinstance(evidence, list) or not evidence
                or any(not required_text(ref) for ref in evidence)):
            errors.append(f"{label}.evidence must be nonempty text")
        if any(credential_bearing_text(item.get(field)) for field in DEVIATION_TEXT_FIELDS):
            errors.append("deviation contains credential-bearing text")
        if isinstance(evidence, list) and any(credential_bearing_text(ref) for ref in evidence):
            errors.append("deviation contains credential-bearing text")
