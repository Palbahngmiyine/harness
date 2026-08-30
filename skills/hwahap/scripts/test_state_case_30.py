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
        def test_add_unit_command_drift_records_only_command_digest(self) -> None:
            run_dir = self.prepare_locked_run_for_add_unit()
            command = "pytest -k command-drift"
            args = Namespace(workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
                             title="outside command", allowed_path=["src"], acceptance_command=[command])
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.add_unit(args)
            self.assertEqual(raised.exception.code, "HW_SCOPE_DRIFT")
            run_bytes = (run_dir / "run.json").read_text()
            events_bytes = (run_dir / "events.jsonl").read_text()
            digest = "sha256:" + hashlib.sha256(command.encode()).hexdigest()
            self.assertIn(digest, run_bytes)
            self.assertIn(digest, events_bytes)
            self.assertNotIn(command, run_bytes)
            self.assertNotIn(command, events_bytes)
            self.validate()

        def test_add_unit_scope_drift_rolls_back_run_and_events_on_validation_failure(self) -> None:
            run_dir = self.prepare_locked_run_for_add_unit()
            state_paths = (run_dir / "run.json", run_dir / "events.jsonl")
            before = tuple(path.read_bytes() for path in state_paths)
            original_validate = hwahap_state.validate_run
            calls = 0

            def fail_after_initial(namespace: Namespace) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise hwahap_state.HwahapError("HW_STATE_INVALID", "forced validation failure")
                original_validate(namespace)

            args = Namespace(workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
                             title="outside path", allowed_path=["docs"], acceptance_command=["test"])
            with patch.object(hwahap_state, "validate_run", side_effect=fail_after_initial):
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.add_unit(args)
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertEqual(tuple(path.read_bytes() for path in state_paths), before)
            self.assertFalse((run_dir / "units" / "unit-1.json").exists())

        def test_add_unit_scope_drift_event_write_failure_restores_run(self) -> None:
            run_dir = self.prepare_locked_run_for_add_unit()
            contract_path, run_path, events_path = (run_dir / "contract.json", run_dir / "run.json", run_dir / "events.jsonl")
            state_paths = (contract_path, run_path, events_path)
            before = tuple(path.read_bytes() for path in state_paths)
            original_replace = hwahap_state._atomic_replace_bytes
            failed = False

            def fail_events(path: Path, *values: object, **kwargs: object) -> None:
                nonlocal failed
                if path == events_path and not failed:
                    failed = True
                    raise OSError("secret drift event write")
                original_replace(path, *values, **kwargs)

            with patch.object(hwahap_state, "_atomic_replace_bytes", new=fail_events):
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.add_unit(Namespace(
                        workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
                        title="outside path", allowed_path=["docs"], acceptance_command=["test"]))
            self.assertEqual(raised.exception.code, "HW_REPORT_GENERATION_FAILED")
            self.assertNotIn("secret drift event write", str(raised.exception))
            self.assertEqual(tuple(path.read_bytes() for path in state_paths), before)
            self.assertFalse((run_dir / "units" / "unit-1.json").exists())
