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
        def test_workspace_ancestor_symlink_rejected_by_all_entrypoints_without_writes(self) -> None:
            target_parent = self.workspace / "target-parent"
            real = target_parent / "project"
            real.mkdir(parents=True)
            spec = real / "spec.md"
            spec.write_text(self.spec.read_text(encoding="utf-8"), encoding="utf-8")
            self.install_agents(real)
            hwahap_state.init_run(Namespace(workspace=str(real), goal_id="test-goal", spec=str(spec)))
            run_dir = real / ".hwahap" / "runs" / "test-goal"
            before = {path.relative_to(real): path.read_bytes() for path in run_dir.rglob("*") if path.is_file()}
            alias_parent = self.workspace / "alias-parent"
            alias_parent.symlink_to(target_parent, target_is_directory=True)
            alias = alias_parent / "project"
            calls = [
                ("init", lambda: hwahap_state.init_run(Namespace(workspace=str(alias), goal_id="test-goal", spec=str(spec)))),
                ("validate", lambda: hwahap_state.validate_run(Namespace(workspace=str(alias), run_id="test-goal"))),
                ("lock", lambda: hwahap_state.lock_contract(Namespace(workspace=str(alias), run_id="test-goal", actor="sol", reason="lock", evidence_ref=["spec.md"]))),
                ("add-unit", lambda: hwahap_state.add_unit(Namespace(workspace=str(alias), run_id="test-goal", unit_id="u", title="u", allowed_path=["src"], acceptance_command=["test"]))),
            ]
            move = self.transition_args("run", "implementing")
            move.workspace = str(alias)
            calls.append(("transition", lambda: hwahap_state.transition(move)))
            for name, call in calls:
                try:
                    with redirect_stdout(io.StringIO()):
                        call()
                except hwahap_state.HwahapError as raised:
                    self.assertEqual(raised.code, "HW_STATE_INVALID", name)
                else:
                    self.fail(name)
                after = {path.relative_to(real): path.read_bytes() for path in run_dir.rglob("*") if path.is_file()}
                self.assertEqual(after, before)

        def test_symlink_spec_and_windows_drive_relative_path_are_rejected(self) -> None:
            source = self.workspace / "real-spec.md"
            source.write_text(self.spec.read_text(encoding="utf-8"), encoding="utf-8")
            link = self.workspace / "spec-link.md"
            link.symlink_to(source)
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.init_run(Namespace(workspace=str(self.workspace), goal_id="link-spec", spec=str(link)))
            self.assertEqual(raised.exception.code, "HW_SPEC_UNCONFIRMED")
            self.assertFalse((self.workspace / ".hwahap").exists())
            self.assertFalse(hwahap_state.safe_relative_path("C:foo"))

        def test_validate_rechecks_spec_hash_and_frontmatter(self) -> None:
            self.init_run()
            self.spec.write_text(
                "---\ntitle: Test goal\nstatus: prfaq\nconfirmed_at: 2026-08-27T00:00:00Z\n---\nchanged body\n",
                encoding="utf-8",
            )
            self.assert_invalid("approved spec source hash does not match")

        def test_persisted_spec_source_rejects_symlink_before_and_after_lock(self) -> None:
            run_dir = self.init_run()
            original = self.spec.read_bytes()
            target = self.workspace / "spec-target.md"
            target.write_bytes(original)
            for locked in (False, True):
                with self.subTest(locked=locked):
                    if self.spec.exists() or self.spec.is_symlink():
                        self.spec.unlink()
                    self.spec.symlink_to(target)
                    contract_path = run_dir / "contract.json"
                    contract = json.loads(contract_path.read_text())
                    if locked:
                        for field in hwahap_state.CONTRACT_LISTS:
                            contract[field] = ["src" if field == "allowed_paths" else "test" if field == "test_commands" else "entry"]
                        contract["locked"] = True
                        contract["lock_sha256"] = hwahap_state.canonical_contract_digest(contract)
                    self.write_json(contract_path, contract)
                    self.assert_invalid("approved spec source")
                    self.spec.unlink()
                    self.spec.write_bytes(original)
