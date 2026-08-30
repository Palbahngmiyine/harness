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
        def test_approved_spec_and_report_validation_failures_are_generic(self) -> None:
            self.init_run()
            marker = "Authorization: Bearer /private/tmp/spec-canary"
            original_read = Path.read_bytes
            def fail_spec(path: Path, *args: object, **kwargs: object):
                if path == self.spec:
                    raise OSError(marker)
                return original_read(path, *args, **kwargs)
            with patch.object(Path, "read_bytes", new=fail_spec):
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    self.validate()
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertNotIn(marker, str(raised.exception))
            run_dir = self.prepare_final_review()
            with redirect_stdout(io.StringIO()):
                hwahap_state.complete_run(self.complete_args())
            marker = "Proxy-Authorization: Digest /private/tmp/report-canary"
            original_module = hwahap_state.report_module
            class BrokenReport:
                def build_payload(self, *args: object): raise ValueError(marker)
            hwahap_state.report_module = lambda: BrokenReport()
            try:
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    self.validate()
            finally:
                hwahap_state.report_module = original_module
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertNotIn(marker, str(raised.exception))
            stderr = io.StringIO()
            hwahap_state.report_module = lambda: BrokenReport()
            try:
                with patch.object(sys, "argv", ["hwahap_state.py", "validate", "--workspace", str(self.workspace), "--run-id", "test-goal"]):
                    with redirect_stderr(stderr):
                        self.assertEqual(hwahap_state.main(), 1)
            finally:
                hwahap_state.report_module = original_module
            self.assertNotIn(marker, stderr.getvalue())

        def test_installed_agent_verification_rejects_codex_ancestor_alias(self) -> None:
            project = self.workspace / "alias-project"
            project.mkdir()
            spec = project / "spec.md"
            spec.write_text(self.spec.read_text(encoding="utf-8"), encoding="utf-8")
            external = self.workspace / "external-agents"
            external.mkdir()
            self.install_agents(external)
            (project / ".codex").symlink_to(external / ".codex", target_is_directory=True)
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.init_run(Namespace(workspace=str(project), goal_id="alias", spec=str(spec)))
            self.assertEqual(raised.exception.code, "HW_AGENT_CONFIG_INVALID")

        def test_changed_spec_for_existing_goal_is_rejected(self) -> None:
            self.init_run()
            self.spec.write_text(
                "---\ntitle: Changed goal\nstatus: prfaq\nconfirmed_at: 2026-08-27T00:00:00Z\n---\n",
                encoding="utf-8",
            )
            args = Namespace(workspace=str(self.workspace), goal_id="test-goal", spec=str(self.spec))
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.init_run(args)
            self.assertEqual(raised.exception.code, "HW_RUN_EXISTS")

        def test_agent_profiles_are_required_and_pinned(self) -> None:
            missing = self.workspace / "missing-agents"
            missing.mkdir()
            spec = missing / "spec.md"
            spec.write_text(self.spec.read_text(encoding="utf-8"), encoding="utf-8")
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.init_run(Namespace(workspace=str(missing), goal_id="test-goal", spec=str(spec)))
            self.assertEqual(raised.exception.code, "HW_AGENT_CONFIG_INVALID")

            self.init_run()
            profile = self.workspace / ".codex" / "agents" / "hwahap-luna-verifier.toml"
            profile.write_text("name = 'changed'\n", encoding="utf-8")
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                self.validate()
            self.assertEqual(raised.exception.code, "HW_AGENT_CONFIG_INVALID")
            self.assertIn("agent profile differs", str(raised.exception))
