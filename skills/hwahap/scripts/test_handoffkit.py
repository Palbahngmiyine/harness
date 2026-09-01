"""Shared valid align-goal handoff fixture."""
try:
    from .test_statekit_base import *
except ImportError:
    from test_statekit_base import *


def write_goal_artifact(workspace: Path, change=None) -> Path:
    spec = {"id": "S1", "kind": "behavior", "statement": "emit report",
            "provenance": {"mode": "choice", "choice_ids": ["C1"],
                           "fact_ids": [], "derivation": None}}
    check = {"id": "A1", "spec_ids": ["S1"], "setup": "repo", "input": "run",
             "action": "finish", "observable_or_inspection": "report exists",
             "pass_condition": "trace is present", "evidence": "report-data.json",
             "acceptance_type": "functional", "measurement": None}
    unit = {"id": "U1", "title": "report", "spec_ids": ["S1"],
            "acceptance_ids": ["A1"], "inputs": ["goal"], "outputs": ["report"],
            "change_boundary": ["skills/hwahap"], "forbidden_changes": ["other"],
            "dependency_unit_ids": [], "execution_order": 1,
            "completion_evidence": ["focused test"]}
    contract = {"contract_version": "align-goal/v1", "revision": 1,
        "target": "implementation", "goal": {"statement": "trace goal",
        "success": ["report"], "failure": ["missing"], "non_goals": ["other"]},
        "repository_context": {"root": ".", "captured_at": "now", "entries": []},
        "facts": [], "choices": [{"id": "C1", "status": "confirmed"}],
        "question_rounds": [], "decision_surfaces": [], "specifications": [spec],
        "acceptance_checks": [check], "implementation_units": [unit], "open_items": []}
    digest = hwahap_state.align_digest({key: contract[key]
        for key in hwahap_state.ALIGN_PROJECTION_KEYS})
    ambiguity = {"review_id": "R1", "status": "pass", "spec_digest": digest}
    cold = {"review_id": "R2", "status": "pass", "spec_digest": digest}
    handoff = {"exact_response": "CONFIRM HANDOFF: ready", "spec_digest": digest,
        "confirmed_at": "2026-09-01T00:03:00Z", "response_ref": {
            "hash": "sha256:" + "a" * 64},
        "ambiguity_receipt_digest": hwahap_state.align_digest(ambiguity),
        "cold_receipt_digest": hwahap_state.align_digest(cold)}
    contract.update({"reviews": {"ambiguity_auditor": ambiguity,
        "cold_consumer": cold}, "confirmations": {"alignment_summary": {},
        "handoff_document": handoff}})
    if change:
        change(contract)
    path = workspace / "goal.md"
    front = ("---\nschema: align-goal/v1\ntitle: trace goal\ntarget: implementation\n"
        "session_status: complete\nalignment_status: aligned\nhandoff_status: ready\n"
        "revision: 1\ncreated: 2026-09-01T00:00:00Z\nupdated: 2026-09-01T00:03:00Z\n"
        "response_log: goal.responses.jsonl\n---\n")
    path.write_text(front + "```json align-goal-contract\n" +
        json.dumps(contract, ensure_ascii=False) + "\n```\n", encoding="utf-8")
    return path
