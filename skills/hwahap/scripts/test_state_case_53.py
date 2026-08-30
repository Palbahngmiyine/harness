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
        def test_curl_credentials_are_rejected_without_echoing_values(self) -> None:
            continuation = "curl " + chr(92) + "\n  --user audit:linecase URL"
            continuation_crlf = "curl " + chr(92) + "\r\n  --user audit:crlfcase URL"
            values = ("curl -u user:pass URL", "curl -uuser:pass URL", continuation,
                      continuation_crlf,
                      "curl --user user:pass", "curl --user=user:pass",
                      "curl -Uuser:pass URL", "curl --proxy-user user:pass",
                      "curl --proxy-user=user:pass", "curl --oauth2-bearer secret",
                      "curl --oauth2-bearer=secret")
            for value in values:
                with self.subTest(value=value):
                    self.assertTrue(hwahap_state.credential_bearing_text(value))
                    self.assertFalse(hwahap_state.safe_test_command(value))
            harmless = "curlish --user documentation"
            self.assertFalse(hwahap_state.credential_bearing_text(harmless))
            self.assertTrue(hwahap_state.safe_test_command(harmless))
            run_dir = self.init_run()
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            for value in values:
                with self.subTest(rejected=value):
                    run["goal_link"]["current"]["reason"] = value
                    self.write_json(run_path, run)
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        self.validate()
                    self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                    self.assertNotIn(value, str(raised.exception))

        def test_init_rejects_credential_bearing_title_before_creating_state(self) -> None:
            for title in ("OPENAI_API_KEY:=init-secret", "SECRET_KEY=init-secret"):
                with self.subTest(title=title):
                    self.spec.write_text(
                        f"---\ntitle: {title}\nstatus: prfaq\nconfirmed_at: 2026-08-27T00:00:00Z\n---\n",
                        encoding="utf-8",
                    )
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        hwahap_state.init_run(Namespace(
                            workspace=str(self.workspace), goal_id="secret-title", spec=str(self.spec)))
                    self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                    self.assertNotIn("init-secret", str(raised.exception))
                    self.assertFalse((self.workspace / ".hwahap").exists())

            source = self.workspace / "SECRET_KEY=init-secret.md"
            source.write_text(self.spec.read_text(encoding="utf-8").replace(
                "title: SECRET_KEY=init-secret", "title: Safe source"), encoding="utf-8")
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.init_run(Namespace(
                    workspace=str(self.workspace), goal_id="secret-source", spec=str(source)))
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertNotIn("init-secret", str(raised.exception))
            self.assertFalse((self.workspace / ".hwahap").exists())
