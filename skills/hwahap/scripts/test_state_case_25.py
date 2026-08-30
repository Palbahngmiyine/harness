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
        def test_state_rejects_one_file_hwahap_source_before_init(self) -> None:
            source = self.workspace / "one-profile-source"
            source.mkdir()
            source.joinpath("hwahap-luna-implementer.toml").write_bytes(
                installer.source_profiles()[0][1])
            with patch.object(hwahap_state, "AGENT_PROFILE_DIR", source):
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.init_run(Namespace(
                        workspace=str(self.workspace), goal_id="one-source", spec=str(self.spec)))
            self.assertEqual(raised.exception.code, "HW_AGENT_CONFIG_INVALID")
            self.assertFalse((self.workspace / ".hwahap").exists())

        def test_state_rejects_extra_hwahap_but_preserves_unrelated_profile(self) -> None:
            agents = self.workspace / ".codex" / "agents"
            for index, name in enumerate(("HWAHAP-extra.toml", "HWAHAP-extra.TOML")):
                (agents / name).write_text('name = "hwahap-extra"\n', encoding="utf-8")
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    self.init_run(f"extra-{index}")
                self.assertEqual(raised.exception.code, "HW_AGENT_CONFIG_INVALID")
                self.assertFalse((self.workspace / ".hwahap" / "runs" / f"extra-{index}").exists())
                (agents / name).unlink()
            self.init_run()
            unrelated = agents / "user-agent.toml"
            unrelated.write_text('name = "user-agent"\n', encoding="utf-8")
            for name in ("HWAHAP-extra.toml", "HWAHAP-extra.TOML"):
                (agents / name).write_text('name = "hwahap-extra"\n', encoding="utf-8")
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    self.validate()
                self.assertEqual(raised.exception.code, "HW_AGENT_CONFIG_INVALID")
                (agents / name).unlink()
            self.assertEqual(unrelated.read_text(encoding="utf-8"), 'name = "user-agent"\n')

        def test_symlinked_hwahap_is_rejected(self) -> None:
            target = self.workspace / "state-target"
            target.mkdir()
            os.symlink(target, self.workspace / ".hwahap")
            args = Namespace(workspace=str(self.workspace), goal_id="test-goal", spec=str(self.spec))
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.init_run(args)
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")

        def test_symlink_workspace_is_rejected_before_resolve(self) -> None:
            target = self.workspace / "real-workspace"
            target.mkdir()
            link = self.workspace / "workspace-link"
            link.symlink_to(target, target_is_directory=True)
            args = Namespace(workspace=str(link), goal_id="test-goal", spec=str(self.spec))
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.init_run(args)
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")

        def test_init_distinguishes_workspace_and_spec_types(self) -> None:
            cases = (
                (self.workspace / "missing-workspace", self.spec, "HW_STATE_INVALID"),
                (self.workspace / "workspace-file", self.spec, "HW_STATE_INVALID"),
                (self.workspace, self.workspace / "spec-directory", "HW_SPEC_UNCONFIRMED"),
            )
            cases[1][0].write_text("not a workspace\n", encoding="utf-8")
            cases[2][1].mkdir()
            for index, (workspace, spec, code) in enumerate(cases):
                with self.subTest(index=index):
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        hwahap_state.init_run(Namespace(
                            workspace=str(workspace), goal_id=f"type-{index}", spec=str(spec)))
                    self.assertEqual(raised.exception.code, code)
