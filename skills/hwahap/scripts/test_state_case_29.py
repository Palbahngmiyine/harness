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
        def test_lock_add_unit_and_transition_commands(self) -> None:
            run_dir = self.init_run()
            contract_path = run_dir / "contract.json"
            contract = json.loads(contract_path.read_text())
            for field in hwahap_state.CONTRACT_LISTS:
                contract[field] = ["src" if field == "allowed_paths" else "test" if field == "test_commands" else "entry"]
            self.write_json(contract_path, contract)
            self.bind_goal()
            with redirect_stdout(io.StringIO()):
                hwahap_state.lock_contract(Namespace(
                    workspace=str(self.workspace), run_id="test-goal", actor="sol-1",
                    reason="approved contract", evidence_ref=["spec.md"],
                ))
                hwahap_state.add_unit(Namespace(
                    workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
                    title="one observable change", allowed_path=["src"], acceptance_command=["test"],
                ))
                hwahap_state.transition(self.transition_args("run", "implementing"))
                hwahap_state.transition(self.transition_args("unit-1", "implementing"))
                hwahap_state.transition(self.transition_args("run", "reviewing"))
                hwahap_state.transition(self.transition_args("unit-1", "reviewing", review_round=1))
            self.validate()
            self.assertEqual(json.loads((run_dir / "run.json").read_text())["metrics"]["unit_count"], 1)
            self.assertTrue(json.loads(contract_path.read_text())["lock_sha256"].startswith("sha256:"))
            self.assertEqual(json.loads((run_dir / "units" / "unit-1.json").read_text())["improvement_history"], [])
            event_lines = (run_dir / "events.jsonl").read_text().splitlines()
            self.assertEqual([json.loads(line)["sequence"] for line in event_lines], [1, 2, 3, 4, 5])

            unit_path = run_dir / "units" / "unit-1.json"
            before_unit, before_events = unit_path.read_bytes(), (run_dir / "events.jsonl").read_bytes()
            with self.assertRaises(hwahap_state.HwahapError):
                with redirect_stdout(io.StringIO()):
                    hwahap_state.transition(self.transition_args("unit-1", "passed", review_round=1))
            self.assertEqual(unit_path.read_bytes(), before_unit)
            self.assertEqual((run_dir / "events.jsonl").read_bytes(), before_events)

        def test_lock_restores_all_state_on_event_write_error(self) -> None:
            run_dir = self.init_run()
            contract_path, run_path, events_path = (run_dir / "contract.json", run_dir / "run.json", run_dir / "events.jsonl")
            contract = json.loads(contract_path.read_text())
            for field in hwahap_state.CONTRACT_LISTS:
                contract[field] = ["src" if field == "allowed_paths" else "test" if field == "test_commands" else "entry"]
            self.write_json(contract_path, contract)
            self.bind_goal()
            state_paths = (contract_path, run_path, events_path)
            before = tuple(path.read_bytes() for path in state_paths)
            original_write_text = Path.write_text

            def fail_events(path: Path, *args: object, **kwargs: object) -> int:
                if path == events_path:
                    raise OSError("injected event write")
                return original_write_text(path, *args, **kwargs)

            with patch.object(Path, "write_text", new=fail_events):
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.lock_contract(Namespace(
                        workspace=str(self.workspace), run_id="test-goal", actor="sol-1",
                        reason="lock", evidence_ref=["contract.json"]))
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertNotIn("injected event write", str(raised.exception))
            self.assertEqual(tuple(path.read_bytes() for path in state_paths), before)

        def test_add_unit_path_drift_waits_for_user_and_creates_no_unit(self) -> None:
            run_dir = self.prepare_locked_run_for_add_unit()
            args = Namespace(workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
                             title="outside path", allowed_path=["docs"], acceptance_command=["test"])
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.add_unit(args)
            self.assertEqual(raised.exception.code, "HW_SCOPE_DRIFT")
            run = json.loads((run_dir / "run.json").read_text())
            self.assertEqual(run["status"], "awaiting_user")
            self.assertEqual(run["failure"]["code"], "HW_SCOPE_DRIFT")
            self.assertIn("docs", run["failure"]["evidence"][0])
            self.assertIn("user", run["failure"]["recovery"])
            self.assertIn("Goal", run["failure"]["recovery"])
            self.assertFalse((run_dir / "units" / "unit-1.json").exists())
            event = json.loads((run_dir / "events.jsonl").read_text().splitlines()[-1])
            self.assertEqual({event["entity"], event["from"], event["to"], event["actor"], event["role"]},
                             {"run", "contract_locked", "awaiting_user", "hwahap-sol-orchestrator", "orchestrator"})
            self.validate()
