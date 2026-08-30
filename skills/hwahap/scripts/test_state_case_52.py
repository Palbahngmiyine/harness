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
        def test_assignment_credential_grammar_is_case_insensitive_and_stable(self) -> None:
            rejected = (
                "CLIENT-SECRET=assignment-sentinel", "github-token:=assignment-sentinel",
                "service password : assignment-sentinel", "x-api-key=assignment-sentinel",
                "private key:assignment-sentinel", "client-secret=\nassignment-sentinel",
                "client-secret=\r\nassignment-sentinel", "client-secret=\rassignment-sentinel",
                "client-secret=\\\nassignment-sentinel", "client\fsecret=assignment-sentinel",
                "client\vsecret=assignment-sentinel", "client\u00a0secret=assignment-sentinel",
                "client-secret=[redacted] assignment-sentinel",
                "client-secret=[redacted]\r\n\tresponse=assignment-sentinel",
                "CLIENT-SECRET=<assignment-sentinel>",
                "github-token:=pre<assignment-sentinel>post",
                "service-password:\"<assignment-sentinel>\"",
                "client secret: <assignment-sentinel>",
                "x-api-key=<assignment-sentinel>", "private key:=<assignment-sentinel>",
            )
            for value in rejected:
                with self.subTest(value=value):
                    self.assertTrue(hwahap_state.credential_bearing_text(value))
            for value in ("secret handling", "token usage unavailable", "client-secretary=value", "tokenization=value"):
                self.assertFalse(hwahap_state.credential_bearing_text(value))
            self.assertFalse(hwahap_state.credential_bearing_text("client-secret=[redacted]"))
            run_dir = self.init_run()
            run_path = run_dir / "run.json"
            original = run_path.read_bytes()
            for value in rejected:
                run = json.loads(original)
                run["goal_link"]["current"]["reason"] = value
                run["goal_link"]["current"]["evidence"] = [value]
                self.write_json(run_path, run)
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    self.validate()
                self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                self.assertNotIn("assignment-sentinel", str(raised.exception))
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    self.assertEqual(hwahap_state.main([
                        "validate", "--workspace", str(self.workspace), "--run-id", "test-goal"]), 1)
                self.assertEqual(stderr.getvalue(), "HW_STATE_INVALID: state is invalid\n")
                run_path.write_bytes(original)

        def test_prefixed_assignment_credentials_are_rejected_in_nested_state(self) -> None:
            values = ("CLIENT-SECRET=state-assignment-sentinel", "github-token:=state-assignment-sentinel",
                      "service-password: state-assignment-sentinel", "client secret=state-assignment-sentinel",
                      "x-api-key=state-assignment-sentinel", "private key=state-assignment-sentinel")
            run_dir = self.init_run()
            run_path = run_dir / "run.json"
            original = run_path.read_bytes()
            for value in values:
                with self.subTest(value=value):
                    run = json.loads(original)
                    run["goal_link"]["current"]["reason"] = value
                    self.write_json(run_path, run)
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        self.validate()
                    self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                    self.assertNotIn("state-assignment-sentinel", str(raised.exception))
                    run_path.write_bytes(original)
