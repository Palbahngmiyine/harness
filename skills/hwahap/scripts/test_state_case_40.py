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
        def test_pending_improvement_allows_terminal_failure_with_evidence(self) -> None:
            run_dir = self.prepare_pending_improvement_run()
            with redirect_stdout(io.StringIO()):
                hwahap_state.transition(self.transition_args(
                    "run", "blocked", failure_code="HW_IMPLEMENTATION_BLOCKED",
                    failure_reason="stop", failure_evidence=["review failed"], failure_recovery="ask user"))
            self.validate()

        def test_validate_rejects_unit_filename_internal_id_mismatch(self) -> None:
            run_dir = self.prepare_locked_planned_unit()
            unit = json.loads((run_dir / "units" / "unit-1.json").read_text())
            (run_dir / "units" / "unit-1.json").unlink()
            self.write_json(run_dir / "units" / "other-unit.json", unit)
            self.assert_invalid()

        def test_validate_rejects_unsafe_unit_filename_and_internal_id(self) -> None:
            run_dir = self.prepare_locked_planned_unit()
            unit_path = run_dir / "units" / "unit-1.json"
            unit = json.loads(unit_path.read_text())
            unit_path.unlink()
            unsafe_filename = run_dir / "units" / "unit_1.json"
            self.write_json(unsafe_filename, unit)
            self.assert_invalid()

            unsafe_filename.unlink()
            unit["unit_id"] = "../victim"
            self.write_json(run_dir / "units" / "unit-1.json", unit)
            self.assert_invalid()

        def test_validate_rejects_every_unexpected_units_entry(self) -> None:
            run_dir = self.prepare_locked_planned_unit()
            units = run_dir / "units"
            unit_bytes = (units / "unit-1.json").read_bytes()
            entries = (
                ("notes.txt", lambda path: path.write_bytes(b"ignored")),
                ("unsafe_name.json", lambda path: path.write_bytes(unit_bytes)),
                ("link.json", lambda path: path.symlink_to(units / "unit-1.json")),
                ("nested", lambda path: path.mkdir()),
            )
            for name, create in entries:
                with self.subTest(name=name):
                    path = units / name
                    create(path)
                    self.assert_invalid("units contains an unexpected entry")
                    path.unlink() if path.is_symlink() or path.is_file() else path.rmdir()

        def test_units_entry_errors_do_not_echo_names_on_validate_or_reinit(self) -> None:
            run_dir = self.init_run()
            for name in ("secret_key=credential-canary.txt", "unsafe_name.json"):
                with self.subTest(name=name):
                    path = run_dir / "units" / name
                    path.write_bytes(b"canary")
                    for action in (lambda: self.validate(), lambda: self.init_run()):
                        with self.assertRaises(hwahap_state.HwahapError) as raised:
                            action()
                        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                        self.assertNotIn(name, str(raised.exception))
                        self.assertNotIn(str(self.workspace), str(raised.exception))
                    path.unlink()
