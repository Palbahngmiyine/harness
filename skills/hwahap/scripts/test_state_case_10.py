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
        def test_final_review_aggregate_matrix_is_enforced_before_completion(self) -> None:
            run_dir = self.prepare_final_review()
            run_path = run_dir / "run.json"
            digest = self.snapshot["diff_digest"]

            def attempt(effort: str, status: str, thread: str) -> dict:
                return {"model": "gpt-5.6-sol", "effort": effort, "status": status,
                        "thread_id": thread, "evidence": ["review"], "diff_snapshot": copy.deepcopy(self.snapshot),
                        "diff_digest": digest}

            valid = (
                {"status": "pending", "attempts": []},
                {"status": "pending", "attempts": [attempt("ultra", "unsupported", "b")]},
                {"status": "pass", "attempts": [attempt("ultra", "pass", "c")]},
                {"status": "pass", "attempts": [attempt("ultra", "unavailable", "d"), attempt("xhigh", "pass", "e")]},
                {"status": "fail", "attempts": [attempt("ultra", "fail", "f")]},
                {"status": "fail", "attempts": [attempt("ultra", "unsupported", "g"), attempt("xhigh", "unavailable", "h")]},
            )
            for final in valid:
                with self.subTest(final=final):
                    self.write_json(run_path, {**json.loads(run_path.read_text()), "final_review": final})
                    self.validate()

            invalid = (
                {"status": "done", "attempts": []},
                {"status": "pending", "attempts": [attempt("ultra", "fail", "i")]},
                {"status": "pass", "attempts": [attempt("xhigh", "pass", "j")]},
                {"status": "fail", "attempts": [attempt("ultra", "pass", "k")]},
                {"status": "pass", "attempts": [attempt("ultra", "unavailable", "l"), attempt("xhigh", "fail", "m")]},
                {"status": "fail", "attempts": [attempt("ultra", "fail", "n"), attempt("xhigh", "fail", "o"), attempt("xhigh", "fail", "p")]},
            )
            for final in invalid:
                with self.subTest(final=final):
                    self.write_json(run_path, {**json.loads(run_path.read_text()), "final_review": final})
                    self.assert_invalid("aggregate matrix")

        def test_final_review_failure_transition_requires_matching_code(self) -> None:
            run_dir = self.prepare_final_review()
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            run["final_review"] = {"status": "fail", "attempts": [{
                "model": "gpt-5.6-sol", "effort": "ultra", "status": "fail",
                "thread_id": "final-fail", "evidence": ["review"], "diff_snapshot": copy.deepcopy(self.snapshot),
                "diff_digest": self.snapshot["diff_digest"],
            }]}
            self.write_json(run_path, run)
            self.validate()
            before = {name: (run_dir / name).read_bytes() for name in ("run.json", "events.jsonl")}
            with self.assertRaises(hwahap_state.HwahapError):
                hwahap_state.transition(self.transition_args(
                    "run", "awaiting_user", failure_code="HW_MODEL_UNAVAILABLE",
                    failure_reason="review failed", failure_evidence=["review"], failure_recovery="ask user"))
            self.assertEqual(before, {name: (run_dir / name).read_bytes() for name in before})
            with redirect_stdout(io.StringIO()):
                hwahap_state.transition(self.transition_args(
                    "run", "awaiting_user", failure_code="HW_FINAL_REVIEW_FAILED",
                    failure_reason="review failed", failure_evidence=["review"], failure_recovery="ask user"))
            self.validate()

        def test_final_review_rejects_blocked_and_failed_successors(self) -> None:
            run_dir = self.prepare_final_review()
            for target in ("blocked", "failed"):
                with self.subTest(target=target):
                    with self.assertRaises(hwahap_state.HwahapError):
                        hwahap_state.transition(self.transition_args(
                            "run", target, failure_code="HW_FINAL_REVIEW_FAILED",
                            failure_reason="review failed", failure_evidence=["review"], failure_recovery="ask user"))
