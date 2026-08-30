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
        def test_structured_credential_pairs_are_rejected_without_writing_or_echoing(self) -> None:
            pairs = (
                ("client-secret", "pair-client-secret-canary"),
                ("github-token", "pair-github-token-canary"),
                ("service-password", "pair-service-password-canary"),
                ("client\u200bsecret", "pair-unicode-client-secret-canary"),
            )
            run_dir = self.prepare_final_review()
            run_path = run_dir / "run.json"
            baseline_run = json.loads(run_path.read_text())
            for key, secret in pairs:
                with self.subTest(key=key):
                    run = copy.deepcopy(baseline_run)
                    run["deviations"] = [{key: secret, "summary": "bounded deviation",
                                           "root_cause": "cause", "impact": "none",
                                           "prevention": "test", "evidence": ["evidence"]}]
                    run["metrics"]["scope_deviations"] = 1
                    self.write_json(run_path, run)
                    original = {
                        path.relative_to(run_dir): path.read_bytes()
                        for path in run_dir.rglob("*") if path.is_file()
                    }
                    for operation in (self.validate, lambda: hwahap_state.complete_run(self.complete_args())):
                        with self.assertRaises(hwahap_state.HwahapError) as raised:
                            operation()
                        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                        self.assertNotIn(secret, str(raised.exception))
                    current = {
                        path.relative_to(run_dir): path.read_bytes()
                        for path in run_dir.rglob("*") if path.is_file()
                    }
                    self.assertEqual(current, original)
                    self.assertFalse((run_dir / "report-data.json").exists())
                    self.assertFalse((run_dir / "report.html").exists())

        def test_sensitive_key_with_container_value_is_rejected_without_writing(self) -> None:
            run_dir = self.prepare_final_review()
            run_path = run_dir / "run.json"
            baseline_run = json.loads(run_path.read_text())
            for container in (["container-list-raw-canary"],
                              {"nested": {"value": "container-object-raw-canary"}}):
                with self.subTest(container=container):
                    run = copy.deepcopy(baseline_run)
                    run["deviations"] = [{"client-secret": container, "summary": "bounded deviation",
                                           "root_cause": "cause", "impact": "none",
                                           "prevention": "test", "evidence": ["evidence"]}]
                    run["metrics"]["scope_deviations"] = 1
                    self.write_json(run_path, run)
                    original = {
                        path.relative_to(run_dir): path.read_bytes()
                        for path in run_dir.rglob("*") if path.is_file()
                    }
                    canary = json.dumps(container)
                    for operation in (self.validate, lambda: hwahap_state.complete_run(self.complete_args())):
                        with self.assertRaises(hwahap_state.HwahapError) as raised:
                            operation()
                        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                        self.assertNotIn(canary, str(raised.exception))
                    current = {
                        path.relative_to(run_dir): path.read_bytes()
                        for path in run_dir.rglob("*") if path.is_file()
                    }
                    self.assertEqual(current, original)
                    self.assertFalse((run_dir / "report-data.json").exists())
                    self.assertFalse((run_dir / "report.html").exists())

            for key, value in (("ordinary", []), ("status", {"nested": 1}), ("summary", None),
                               ("client-secret", "[redacted]")):
                with self.subTest(allowed_pair=(key, value)):
                    errors: list[str] = []
                    hwahap_state.validate_state_strings({key: value}, "probe", errors)
                    self.assertEqual(errors, [])
