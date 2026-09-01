"""Bind Hwahap execution units to canonical align-goal U/S/A IDs."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())

TRACE_KEYS = {"unit_id", "spec_ids", "acceptance_ids"}


def source_handoff(contract: dict) -> dict | None:
    spec = contract.get("spec")
    if not isinstance(spec, dict) or spec.get("status") != "align-goal":
        return None
    handoff = spec.get("handoff")
    return handoff if isinstance(handoff, dict) else None


def source_unit_trace(contract: dict, source_unit_id: object) -> dict | None:
    handoff = source_handoff(contract)
    if handoff is None:
        if source_unit_id is not None:
            raise HwahapError("HW_STATE_INVALID", "source unit requires an align-goal handoff")
        return None
    if not required_text(source_unit_id):
        raise HwahapError("HW_STATE_INVALID", "align-goal unit requires source-unit-id")
    matches = [item for item in handoff.get("implementation_units", [])
               if isinstance(item, dict) and item.get("id") == source_unit_id]
    if len(matches) != 1:
        raise HwahapError("HW_STATE_INVALID", "source unit is absent or ambiguous")
    source = matches[0]
    return {"unit_id": source_unit_id, "spec_ids": source.get("spec_ids"),
            "acceptance_ids": source.get("acceptance_ids")}


def validate_handoff_units(contract: dict, units: list[dict], complete: bool,
                           errors: list[str]) -> None:
    handoff = source_handoff(contract)
    if handoff is None:
        if any(unit.get("source_trace") not in (None, {}) for unit in units):
            errors.append("source traces require an align-goal handoff")
        return
    expected = {item.get("id"): item for item in handoff.get("implementation_units", [])
                if isinstance(item, dict)}
    mapped = []
    for unit in units:
        trace = unit.get("source_trace")
        source = expected.get(trace.get("unit_id")) if isinstance(trace, dict) else None
        if not isinstance(trace, dict) or set(trace) != TRACE_KEYS or source is None \
                or trace.get("spec_ids") != source.get("spec_ids") \
                or trace.get("acceptance_ids") != source.get("acceptance_ids"):
            errors.append(f"{unit.get('unit_id')}: invalid align-goal source trace")
            continue
        mapped.append(trace["unit_id"])
    if len(mapped) != len(set(mapped)):
        errors.append("align-goal source units must map exactly once")
    if complete and set(mapped) != set(expected):
        errors.append("final review requires complete align-goal unit coverage")
