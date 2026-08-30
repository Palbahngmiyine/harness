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
        def test_other_header_variants_are_rejected_without_write_or_echo(self) -> None:
            run_dir = self.init_run()
            run_path = run_dir / "run.json"
            base = json.loads(run_path.read_text())
            variants = (
                "X-Api-Key: [redacted]\rresponse=state-api-fold-secret",
                "X-Api-Key: state-api-prefix-secret [redacted]",
                "Cookie: [redacted]\r\n\tstate-cookie-fold-secret",
                "Cookie: state-cookie-prefix-secret [redacted]",
                "Password: [redacted]\rstate-password-fold-secret",
                "Password: state-password-prefix-secret [redacted]",
                "x_api_key=Basic state-x-under-basic-secret",
                "x-api-key=Digest state-x-hyphen-digest-secret",
                "x api key: Bearer state-x-spaced-bearer-secret",
                "x_api_key=Basic [redacted]\nSECRET_KEY=state-overlap-secret",
                "Authorization: Basic <state-auth-angle-prefix>",
                "Proxy-Authorization: Digest state-proxy-angle-prefix<state-proxy-angle-suffix>",
                "X-Api-Key: <state-x-angle-prefix>",
                "x_api_key=Basic state-x-under-angle-prefix<state-x-under-angle-suffix>",
                "Cookie: <state-cookie-angle-prefix>",
                "Password: state-password-angle-prefix<state-password-angle-suffix>",
                "Private-Key: <state-private-angle-prefix>",
            )
            safe_variants = ("X-Api-Key: [redacted]", "Cookie: [redacted]", "Password: [redacted]",
                             "x_api_key=Basic [redacted]", "X_API_KEY=Digest [redacted]",
                             "x api key: Bearer [redacted]")
            for safe in safe_variants:
                self.assertFalse(hwahap_state.credential_bearing_text(safe))
                run = copy.deepcopy(base)
                run["goal_link"]["current"]["reason"] = safe
                run["goal_link"]["current"]["evidence"] = [safe]
                self.write_json(run_path, run)
                self.validate()
            for value in variants:
                with self.subTest(value=value):
                    run = copy.deepcopy(base)
                    run["goal_link"]["current"]["reason"] = value
                    run["goal_link"]["current"]["evidence"] = [value]
                    self.write_json(run_path, run)
                    before = {path: path.read_bytes() for path in (run_dir / "contract.json", run_path, run_dir / "events.jsonl")}
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        self.validate()
                    self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                    self.assertNotIn(value.rsplit(" ", 1)[-1], str(raised.exception))
                    self.assertEqual({path: path.read_bytes() for path in before}, before)

        def test_public_cli_errors_are_static_and_registered(self) -> None:
            self.assertTrue(set(hwahap_state.FAILURE_CODES) <= set(hwahap_state.PUBLIC_ERROR_MESSAGES))
            action = next(action for action in hwahap_state.parser()._actions if getattr(action, "choices", None))
            self.assertTrue(all(callable(command.get_default("handler")) for command in action.choices.values()))
            marker = "Authorization: Bearer /private/tmp/cli-canary"
            cases = (["unknown", marker], ["validate"], ["goal-sync", "--mode", "invalid"])
            for argv in cases:
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    self.assertEqual(hwahap_state.main(argv), 1)
                self.assertEqual(stderr.getvalue(), "HW_STATE_INVALID: state is invalid\n")
                self.assertNotIn(marker, stderr.getvalue())
            with patch.object(hwahap_state, "validate_run", side_effect=RuntimeError(marker)):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    self.assertEqual(hwahap_state.main(["validate", "--workspace", marker, "--run-id", "run"]), 1)
                self.assertEqual(stderr.getvalue(), "HW_STATE_INVALID: command failed\n")

        def test_units_read_failure_is_stable_at_cli_boundary(self) -> None:
            self.init_run()
            marker = "Proxy-Authorization: Digest /private/tmp/units-canary"
            before = (self.workspace / ".hwahap" / "runs" / "test-goal" / "run.json").read_bytes()
            with patch.object(hwahap_state, "unit_paths_for_read", side_effect=OSError(marker)):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    self.assertEqual(hwahap_state.main(["validate", "--workspace", str(self.workspace), "--run-id", "test-goal"]), 1)
            self.assertEqual(stderr.getvalue(), "HW_STATE_INVALID: state is invalid\n")
            self.assertNotIn(marker, stderr.getvalue())
            self.assertEqual((self.workspace / ".hwahap" / "runs" / "test-goal" / "run.json").read_bytes(), before)
