"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def validate_events(path: Path, run: dict, units: list[dict], errors: list[str]) -> list[dict]:
    events: list[dict] = []
    try:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            event = json.loads(line)
            if not isinstance(event, dict):
                errors.append(f"events.jsonl line {number} must be an object")
            else:
                events.append(event)
    except (OSError, UnicodeError, json.JSONDecodeError):
        errors.append("invalid events.jsonl")
        return []
    if not events:
        if run.get("status") == "initialized" and not units:
            return events
        errors.append("events.jsonl is required for non-initial state")
        return events
    unit_ids = {unit.get("unit_id") for unit in units if required_text(unit.get("unit_id"))}
    current: dict[str, str] = {"run": "initialized"}
    current.update({unit_id: "planned" for unit_id in unit_ids})
    for expected_sequence, event in enumerate(events, 1):
        if any(field not in event for field in EVENT_FIELDS):
            errors.append(f"events.jsonl sequence {expected_sequence} is incomplete")
            continue
        if event.get("type") != "state_transition":
            errors.append(f"events.jsonl sequence {expected_sequence} has invalid type")
        if event.get("sequence") != expected_sequence or not isinstance(event.get("sequence"), int) or isinstance(event.get("sequence"), bool):
            errors.append("event sequence must be contiguous starting at 1")
        if any(not required_text(event.get(field)) for field in ("timestamp", "type", "entity", "from", "to", "actor", "role", "reason", "input_digest")):
            errors.append(f"events.jsonl sequence {expected_sequence} has invalid text fields")
        review_round = event.get("review_round")
        if not isinstance(review_round, int) or isinstance(review_round, bool) or review_round < 0:
            errors.append(f"events.jsonl sequence {expected_sequence} has invalid review_round")
        refs = event.get("evidence_refs")
        if not isinstance(refs, list) or not refs or any(not required_text(ref) for ref in refs):
            errors.append(f"events.jsonl sequence {expected_sequence} has invalid evidence_refs")
        entity = event.get("entity")
        if not isinstance(entity, str) or entity not in current:
            errors.append(f"events.jsonl entity is unknown: {entity}")
            continue
        if entity != "run" and current.get("run") in RUN_UNIT_MUTATION_BLOCKED_STATES:
            if current.get("run") in RUN_TERMINAL_STATES:
                errors.append(f"terminal run cannot have unit successors: {entity}")
            else:
                errors.append(f"final_review run cannot have unit successors: {entity}")
        source, target = event.get("from"), event.get("to")
        if not isinstance(source, str) or source != current[entity]:
            errors.append(f"events.jsonl current state mismatch for {entity}")
        graph = RUN_TRANSITIONS if entity == "run" else UNIT_TRANSITIONS
        if isinstance(source, str) and source in (RUN_TERMINAL_STATES if entity == "run" else UNIT_TERMINAL_STATES):
            errors.append(f"terminal state cannot have successors: {entity}")
        elif (not isinstance(source, str) or not isinstance(target, str)
              or target not in graph.get(source, set())):
            errors.append(f"illegal transition for {entity}: {source} -> {target}")
        if entity != "run" and isinstance(target, str):
            required_run = {"implementing": "implementing", "reviewing": "reviewing",
                            "passed": "reviewing", "recovery": "recovering",
                            "replan_required": "replanning"}.get(target)
            if required_run and current.get("run") != required_run:
                errors.append(f"unit transition requires run status {required_run}")
            elif target in {"blocked", "failed", "awaiting_user"} and current.get("run") not in {
                    "implementing", "reviewing", "recovering", "replanning"}:
                errors.append("unit terminal transition requires an active run phase")
        if isinstance(target, str):
            current[entity] = target
            if entity != "run":
                unit_states = [value for key, value in current.items() if key != "run"]
                if sum(value not in {"planned", "passed"} for value in unit_states) > 1:
                    errors.append("only one unit may be unresolved")
    if current.get("run") != run.get("status"):
        errors.append("last run transition does not match current status")
    for unit in units:
        unit_id = unit.get("unit_id")
        if required_text(unit_id) and current.get(unit_id, "planned") != unit.get("status"):
            errors.append(f"last unit transition does not match current status: {unit_id}")
    return events
