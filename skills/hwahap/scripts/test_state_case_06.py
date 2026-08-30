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
        def test_improvement_candidate_credentials_are_rejected_without_echo_or_write(self) -> None:
            run_dir = self.prepare_final_review()
            run_path = run_dir / "run.json"
            before = run_path.read_bytes()
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.record_improvement_candidate(
                    self.candidate_args(summary="OPENAI_API_KEY:=candidate-secret"))
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertNotIn("candidate-secret", str(raised.exception))
            self.assertEqual(run_path.read_bytes(), before)

        def test_improvement_candidate_rollback_failure_is_generic(self) -> None:
            run_dir = self.prepare_final_review()
            original_validate = hwahap_state.validate_run
            validations = 0
            def fail_after_write(args: Namespace) -> None:
                nonlocal validations
                validations += 1
                if validations > 1:
                    raise hwahap_state.HwahapError("HW_STATE_INVALID", "/private/tmp/Proxy-Authorization: Digest rollback-canary")
                original_validate(args)
            hwahap_state.validate_run = fail_after_write
            try:
                with patch.object(Path, "write_bytes", side_effect=OSError("/private/tmp/path-canary")):
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        hwahap_state.record_improvement_candidate(self.candidate_args())
            finally:
                hwahap_state.validate_run = original_validate
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertEqual(str(raised.exception), "could not record improvement candidate")
            self.assertNotIn("canary", str(raised.exception))

        def test_improvement_candidate_schema_rejects_missing_extra_and_executable_fields(self) -> None:
            run_dir = self.prepare_final_review()
            with redirect_stdout(io.StringIO()):
                hwahap_state.record_improvement_candidate(self.candidate_args())
            run_path = run_dir / "run.json"
            original = json.loads(run_path.read_text())
            for name, mutate in (
                ("missing", lambda item: item.pop("summary")),
                ("extra", lambda item: item.update({"command": "run candidate"})),
                ("path", lambda item: item.update({"path": "src"})),
                ("unit", lambda item: item.update({"unit_id": "unit-1"})),
            ):
                with self.subTest(name=name):
                    current = copy.deepcopy(original)
                    mutate(current["improvement_candidates"][0])
                    self.write_json(run_path, current)
                    self.assert_invalid("improvement_candidates")

        def test_completion_preserves_proposed_candidate_and_does_not_execute_it(self) -> None:
            run_dir = self.prepare_final_review()
            with redirect_stdout(io.StringIO()):
                hwahap_state.record_improvement_candidate(self.candidate_args())
            with redirect_stdout(io.StringIO()):
                hwahap_state.complete_run(self.complete_args())
            run = json.loads((run_dir / "run.json").read_text())
            self.assertEqual(run["improvement_candidates"][0]["status"], "proposed")
            self.assertEqual(run["improvement_candidates"][0]["summary"], "reduce repeated setup")
            self.validate()

        def test_generic_completed_transition_is_rejected(self) -> None:
            run_dir = self.prepare_final_review()
            before = {name: (run_dir / name).read_bytes() for name in ("run.json", "events.jsonl")}
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.transition(self.transition_args("run", "completed"))
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertEqual(before, {name: (run_dir / name).read_bytes() for name in before})
