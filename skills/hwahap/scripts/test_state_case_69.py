"""Case 69: bind handoff-ready align-goal S/A/U without PRFAQ."""
try:
    from .test_statekit_base import *
    from .test_statekit_01 import *
except ImportError:
    from test_statekit_base import *
    from test_statekit_01 import *


class HwahapStateCase69(StateFixtureMixin01, unittest.TestCase):
    def artifact(self, change=None) -> Path:
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
        path = self.workspace / "goal.md"
        front = ("---\nschema: align-goal/v1\ntitle: trace goal\ntarget: implementation\n"
            "session_status: complete\nalignment_status: aligned\nhandoff_status: ready\n"
            "revision: 1\ncreated: 2026-09-01T00:00:00Z\nupdated: 2026-09-01T00:03:00Z\n"
            "response_log: goal.responses.jsonl\n---\n")
        path.write_text(front + "```json align-goal-contract\n" +
            json.dumps(contract, ensure_ascii=False) + "\n```\n", encoding="utf-8")
        return path

    def test_goal_handoff_initializes_and_revalidates_sealed_projection(self) -> None:
        source = self.artifact()
        with redirect_stdout(io.StringIO()):
            hwahap_state.init_run(Namespace(workspace=str(self.workspace),
                goal_id="aligned-goal", goal_spec=str(source)))
        run_dir = self.workspace / ".hwahap" / "runs" / "aligned-goal"
        saved = json.loads((run_dir / "contract.json").read_text())["spec"]
        self.assertEqual(saved["status"], "align-goal")
        self.assertEqual(set(saved["handoff"]), {"schema", "revision", "spec_digest",
            "specifications", "acceptance_checks", "implementation_units", "confirmation"})
        hwahap_state.validate_run(Namespace(workspace=str(self.workspace),
            run_id="aligned-goal", quiet=True))
        source.write_text(source.read_text() + "changed\n", encoding="utf-8")
        with self.assertRaises(hwahap_state.HwahapError):
            hwahap_state.validate_run(Namespace(workspace=str(self.workspace),
                run_id="aligned-goal", quiet=True))

    def test_goal_handoff_rejects_stale_receipt_and_unmapped_acceptance(self) -> None:
        for change in (lambda c: c["reviews"]["cold_consumer"].update(spec_digest="sha256:" + "b" * 64),
                       lambda c: c["implementation_units"][0].update(acceptance_ids=[])):
            with self.subTest(change=change), self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.load_goal_spec(self.artifact(change))
            self.assertEqual(raised.exception.code, "HW_HANDOFF_UNCONFIRMED")


if __name__ == "__main__":
    unittest.main()
