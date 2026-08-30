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
        def test_add_unit_write_then_raise_restores_state_and_removes_unit(self) -> None:
            run_dir = self.prepare_locked_run_for_add_unit()
            contract_path, run_path, events_path = (run_dir / "contract.json", run_dir / "run.json", run_dir / "events.jsonl")
            unit_path = run_dir / "units" / "unit-1.json"
            state_paths = (contract_path, run_path, events_path)
            before = tuple(path.read_bytes() for path in state_paths)
            original_write_text = Path.write_text

            def write_then_raise(path: Path, *args: object, **kwargs: object) -> int:
                result = original_write_text(path, *args, **kwargs)
                if path == run_path:
                    raise OSError("secret add-unit write")
                return result

            with patch.object(Path, "write_text", new=write_then_raise):
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.add_unit(Namespace(
                        workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
                        title="unit", allowed_path=["src"], acceptance_command=["test"]))
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertNotIn("secret add-unit write", str(raised.exception))
            self.assertEqual(tuple(path.read_bytes() for path in state_paths), before)
            self.assertFalse(unit_path.exists())

        def test_add_unit_unsafe_inputs_preserve_state_and_terminal_repeat_is_read_only(self) -> None:
            run_dir = self.prepare_locked_run_for_add_unit()
            state_paths = (run_dir / "contract.json", run_dir / "run.json", run_dir / "events.jsonl")
            before = tuple(path.read_bytes() for path in state_paths)
            for allowed_path, command in ((["../outside"], "test"), (["src"], "TOKEN=secret test")):
                with self.subTest(allowed_path=allowed_path, command=command):
                    args = Namespace(workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
                                     title="unsafe", allowed_path=allowed_path, acceptance_command=[command])
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        hwahap_state.add_unit(args)
                    self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                    self.assertEqual(tuple(path.read_bytes() for path in state_paths), before)

            drift_args = Namespace(workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
                                   title="outside path", allowed_path=["docs"], acceptance_command=["test"])
            with self.assertRaises(hwahap_state.HwahapError):
                hwahap_state.add_unit(drift_args)
            terminal = tuple(path.read_bytes() for path in state_paths)
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.add_unit(drift_args)
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertEqual(tuple(path.read_bytes() for path in state_paths), terminal)
            self.validate()

        def test_run_test_is_disabled_before_any_state_or_command_access(self) -> None:
            run_dir = self.prepare_test_unit()
            unit_path, events_path, run_path = (run_dir / "units" / "unit-1.json",
                                                run_dir / "events.jsonl", run_dir / "run.json")
            canary = self.workspace.parent / f"run-test-disabled-canary-{self.workspace.name}"
            canary.mkdir()
            marker = canary / "marker"
            marker.write_text("must-survive", encoding="utf-8")
            commands = (f"rm -rf {canary}", "/bin/sh -c 'touch disabled-canary'",
                        "python3 external-script.py", "TOKEN=secret python3 -c 'print(1)'")
            original_run = subprocess.run
            def unexpected(*args: object, **kwargs: object) -> None:
                raise AssertionError("subprocess.run must not be called")
            subprocess.run = unexpected  # type: ignore[assignment]
            try:
                for command in commands:
                    with self.subTest(command=command):
                        unit = json.loads(unit_path.read_text())
                        unit["acceptance_commands"] = [command]
                        self.write_json(unit_path, unit)
                        before = {path: path.read_bytes() for path in (unit_path, events_path, run_path)}
                        with self.assertRaises(hwahap_state.HwahapError) as raised:
                            hwahap_state.run_test(self.run_test_args())
                        self.assertEqual(raised.exception.code, "HW_TEST_EXECUTION_DISABLED")
                        self.assertEqual(str(raised.exception), "test execution is disabled; use an authorized Luna verifier and record-test-receipt")
                        self.assertEqual({path: path.read_bytes() for path in before}, before)
                        self.assertEqual(marker.read_text(encoding="utf-8"), "must-survive")
            finally:
                subprocess.run = original_run  # type: ignore[assignment]
                marker.unlink(missing_ok=True)
                canary.rmdir()
