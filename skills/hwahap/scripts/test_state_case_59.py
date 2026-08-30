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
        def test_final_review_unit_integrity_survives_later_run_states(self) -> None:
            run_dir = self.prepare_final_review()
            unit_path = run_dir / "units" / "unit-1.json"
            tampered = json.loads(unit_path.read_text())
            tampered.update({"status": "planned", "review_history": [], "test_receipts": []})
            self.write_json(unit_path, tampered)
            self.assert_invalid("final_review requires a passed unit")

            run = json.loads((run_dir / "run.json").read_text())
            run["status"] = "final_review"
            run["final_review"] = {"status": "fail", "attempts": [{
                "model": "gpt-5.6-sol", "effort": "ultra", "status": "fail", "thread_id": "final-fail",
                "evidence": ["review"], "diff_snapshot": copy.deepcopy(self.snapshot),
                "diff_digest": self.snapshot["diff_digest"],
            }]}
            self.write_json((run_dir / "run.json"), run)
            self.write_json(unit_path, self.passed_unit())
            self.write_events(run_dir, self.phase_events("passed") + [("run", "reviewing", "final_review")])
            with redirect_stdout(io.StringIO()):
                hwahap_state.transition(self.transition_args(
                    "run", "awaiting_user", failure_code="HW_FINAL_REVIEW_FAILED",
                    failure_reason="review failed", failure_evidence=["review"], failure_recovery="ask user"))
            tampered = json.loads(unit_path.read_text())
            tampered.update({"status": "planned", "review_history": [], "test_receipts": []})
            self.write_json(unit_path, tampered)
            self.assert_invalid("final_review requires a passed unit")

            self.write_json(unit_path, self.passed_unit())
            run = json.loads((run_dir / "run.json").read_text())
            for name in ("report-data.json", "report.html"):
                (run_dir / name).unlink()
            run["report"].update({
                "status": "pending", "source_payload_sha256": None,
                "data": {"path": "report-data.json", "file_sha256": None},
                "html": {"path": "report.html", "file_sha256": None},
                "generated_at": None,
            })
            run["status"] = "final_review"
            run.pop("failure", None)
            run["final_review"] = {"status": "pass", "attempts": [{
                "model": "gpt-5.6-sol", "effort": "ultra", "status": "pass", "thread_id": "final-pass",
                "evidence": ["review"], "diff_snapshot": copy.deepcopy(self.snapshot),
                "diff_digest": self.snapshot["diff_digest"],
            }]}
            self.write_json(run_dir / "run.json", run)
            self.write_events(run_dir, self.phase_events("passed") + [("run", "reviewing", "final_review")])
            with redirect_stdout(io.StringIO()):
                hwahap_state.complete_run(self.complete_args())
            tampered = json.loads(unit_path.read_text())
            tampered.update({"status": "planned", "review_history": [], "test_receipts": []})
            self.write_json(unit_path, tampered)
            self.assert_invalid("final_review requires a passed unit")
