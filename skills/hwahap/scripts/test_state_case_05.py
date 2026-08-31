try:
    from .test_statekit_base import *
    from .test_statekit_01 import *
    from .test_statekit_02 import *
    from .test_statekit_03 import *
    from .test_statekit_04 import *
    from .test_statekit_05 import *
    from .test_statekit_06 import *
except ImportError:
    from test_statekit_base import *
    from test_statekit_01 import *
    from test_statekit_02 import *
    from test_statekit_03 import *
    from test_statekit_04 import *
    from test_statekit_05 import *
    from test_statekit_06 import *

class HwahapStateTests(StateFixtureMixin01, StateFixtureMixin02, StateFixtureMixin03, StateFixtureMixin04, StateFixtureMixin05, StateFixtureMixin06, unittest.TestCase):
        def test_complete_rejects_raw_curl_credential_before_writing_anything(self) -> None:
            run_dir = self.prepare_final_review()
            run_path, events_path, report_path = (run_dir / "run.json", run_dir / "events.jsonl", run_dir / "report.html")
            run = json.loads(run_path.read_text())
            raw = "curl " + chr(92) + "\n  --user audit:linecase URL"
            run["deviations"] = [{"summary": raw, "root_cause": "cause", "impact": "impact",
                                   "prevention": "prevention", "evidence": ["evidence"]}]
            self.write_json(run_path, run)
            before = {path: path.read_bytes() for path in (run_path, events_path)}
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.complete_run(self.complete_args())
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertNotIn("audit:linecase", str(raised.exception))
            self.assertEqual({path: path.read_bytes() for path in before}, before)
            self.assertFalse(report_path.exists())
            run["deviations"][0]["summary"] = "curlish --user documentation"
            self.write_json(run_path, run)
            with redirect_stdout(io.StringIO()):
                hwahap_state.complete_run(self.complete_args())
            self.assertIn("curlish --user documentation", report_path.read_text(encoding="utf-8"))

        def test_improvement_candidate_appends_only_to_final_review_run(self) -> None:
            run_dir = self.prepare_final_review()
            run_path, unit_path, events_path = (run_dir / "run.json", run_dir / "units" / "unit-1.json", run_dir / "events.jsonl")
            before = {path: path.read_bytes() for path in (unit_path, events_path)}
            with redirect_stdout(io.StringIO()):
                hwahap_state.record_improvement_candidate(self.candidate_args())
            run = json.loads(run_path.read_text())
            self.assertEqual(run["improvement_candidates"], [{
                "status": "proposed", "summary": "reduce repeated setup",
                "evidence": ["final-review"], "expected_effect": "fewer manual steps",
                "next_action": "review in a new Goal", "decision_context": {
                    "scenario": "candidate scenario", "affected_scope": "candidate scope",
                    "impact": "candidate impact", "decision_reason": "candidate decision",
                    "evidence_relation": "candidate evidence", "success_condition": "candidate success",
                },
            }])
            self.assertEqual({path: path.read_bytes() for path in before}, before)
            self.validate()

        def test_improvement_candidate_wrong_state_is_byte_identical(self) -> None:
            run_dir = self.init_run()
            run_path = run_dir / "run.json"
            before = run_path.read_bytes()
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.record_improvement_candidate(self.candidate_args())
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertEqual(run_path.read_bytes(), before)

        def test_improvement_candidate_requires_passing_final_review(self) -> None:
            run_dir = self.prepare_final_review()
            run_path = run_dir / "run.json"
            for final in (
                {"status": "pending", "attempts": [{
                    "model": "gpt-5.6-sol", "effort": "ultra", "status": "unsupported",
                    "thread_id": "ultra-pending", "evidence": ["probe"],
                    "diff_snapshot": copy.deepcopy(self.snapshot), "diff_digest": self.snapshot["diff_digest"],
                }]},
                {"status": "fail", "attempts": [{
                    "model": "gpt-5.6-sol", "effort": "ultra", "status": "fail",
                    "thread_id": "ultra-fail", "evidence": ["review"],
                    "diff_snapshot": copy.deepcopy(self.snapshot), "diff_digest": self.snapshot["diff_digest"],
                }]},
            ):
                with self.subTest(final=final):
                    run = json.loads(run_path.read_text())
                    run["final_review"] = final
                    self.write_json(run_path, run)
                    before = run_path.read_bytes()
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        hwahap_state.record_improvement_candidate(self.candidate_args())
                    self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                    self.assertEqual(run_path.read_bytes(), before)
                    run["improvement_candidates"] = [{
                        "status": "proposed", "summary": "candidate", "evidence": ["review"],
                        "expected_effect": "effect", "next_action": "inspect",
                    }]
                    self.write_json(run_path, run)
                    self.assert_invalid("improvement_candidates require")
