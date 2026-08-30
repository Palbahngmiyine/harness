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
        def test_record_improvement_restores_all_state_on_event_write_error(self) -> None:
            run_dir = self.prepare_pending_improvement_run()
            contract_path, run_path = run_dir / "contract.json", run_dir / "run.json"
            unit_path, events_path = run_dir / "units" / "unit-1.json", run_dir / "events.jsonl"
            record = self.improvement_record(1, "terra_recovery")
            args = Namespace(
                workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
                after_round=record["after_round"], kind=record["kind"],
                failure_signature=record["failure_signature"], root_cause=record["root_cause"],
                hypothesis=record["hypothesis"], action=record["action"],
                strategy_digest=record["strategy_digest"], scope_status=record["scope_status"],
                evidence_ref=record["evidence"], actor="sol-1",
            )
            state_paths = (contract_path, run_path, unit_path, events_path)
            before = tuple(path.read_bytes() for path in state_paths)
            original_write_bytes = Path.write_bytes

            def fail_events(path: Path, *values: object, **kwargs: object) -> int:
                if path == events_path:
                    raise OSError("injected event write")
                return original_write_bytes(path, *values, **kwargs)

            with patch.object(Path, "write_bytes", new=fail_events):
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.record_improvement(args)
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertNotIn("injected event write", str(raised.exception))
            self.assertEqual(tuple(path.read_bytes() for path in state_paths), before)

        def test_record_improvement_read_error_is_generic(self) -> None:
            run_dir = self.prepare_pending_improvement_run()
            events_path = run_dir / "events.jsonl"
            record = self.improvement_record(1, "terra_recovery")
            args = Namespace(
                workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
                after_round=record["after_round"], kind=record["kind"],
                failure_signature=record["failure_signature"], root_cause=record["root_cause"],
                hypothesis=record["hypothesis"], action=record["action"],
                strategy_digest=record["strategy_digest"], scope_status=record["scope_status"],
                evidence_ref=record["evidence"], actor="sol-1",
            )
            original_read_bytes = Path.read_bytes

            def fail_events(path: Path, *args: object, **kwargs: object) -> bytes:
                if path == events_path:
                    raise OSError("secret read detail")
                return original_read_bytes(path, *args, **kwargs)

            with patch.object(Path, "read_bytes", new=fail_events):
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.record_improvement(args)
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertNotIn("secret read detail", str(raised.exception))

        def test_pending_improvement_blocks_run_replanning_without_writes(self) -> None:
            run_dir = self.prepare_pending_improvement_run()
            run_path, events_path = run_dir / "run.json", run_dir / "events.jsonl"
            before = run_path.read_bytes(), events_path.read_bytes()
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                with redirect_stdout(io.StringIO()):
                    hwahap_state.transition(self.transition_args("run", "replanning"))
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertIn("pending improvement", str(raised.exception))
            self.assertEqual((run_path.read_bytes(), events_path.read_bytes()), before)

        def test_pending_improvement_rejects_hand_edited_run_replanning(self) -> None:
            run_dir = self.prepare_pending_improvement_run()
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            run["status"] = "replanning"
            self.write_json(run_path, run)
            self.write_events(run_dir, [
                ("run", "initialized", "contract_locked"),
                ("run", "contract_locked", "implementing"),
                ("run", "implementing", "reviewing"),
                ("run", "reviewing", "replanning"),
                ("unit-1", "planned", "implementing"),
                ("unit-1", "implementing", "reviewing"),
            ])
            self.assert_invalid("pending improvement")
