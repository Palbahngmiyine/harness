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
        def test_record_improvement_rejects_preexisting_events_symlink_before_write(self) -> None:
            run_dir = self.init_run()
            unit_path = run_dir / "units" / "unit-1.json"
            unit = self.passed_unit()
            unit["status"] = "reviewing"
            unit["review_history"] = [self.review_round(1, "fail")]
            unit["improvement_history"] = []
            self.write_json(unit_path, unit)
            self.write_events(run_dir, [
                ("unit-1", "planned", "implementing"), ("unit-1", "implementing", "reviewing"),
            ])
            events_path = run_dir / "events.jsonl"
            victim = self.workspace.parent / f"hwahap-events-victim-{self.workspace.name}.jsonl"
            victim.write_bytes(events_path.read_bytes())
            victim_mtime = victim.stat().st_mtime_ns
            events_path.unlink()
            events_path.symlink_to(victim)
            record = self.improvement_record(1, "terra_recovery")
            args = Namespace(
                workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
                after_round=record["after_round"], kind=record["kind"],
                failure_signature=record["failure_signature"], root_cause=record["root_cause"],
                hypothesis=record["hypothesis"], action=record["action"],
                strategy_digest=record["strategy_digest"], scope_status=record["scope_status"],
                evidence_ref=record["evidence"], actor="sol-1",
            )
            before_unit = unit_path.read_bytes()
            before_run = (run_dir / "run.json").read_bytes()
            before_victim = victim.read_bytes()
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                with redirect_stdout(io.StringIO()):
                    hwahap_state.record_improvement(args)
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertEqual(unit_path.read_bytes(), before_unit)
            self.assertEqual((run_dir / "run.json").read_bytes(), before_run)
            self.assertEqual(victim.read_bytes(), before_victim)
            self.assertEqual(victim.stat().st_mtime_ns, victim_mtime)
            self.assertTrue(events_path.is_symlink())
            self.assertEqual(len(victim.read_bytes().splitlines()), 2)

        def test_transition_restores_all_state_on_event_write_error(self) -> None:
            run_dir = self.prepare_locked_planned_unit()
            contract_path, run_path = run_dir / "contract.json", run_dir / "run.json"
            unit_path, events_path = run_dir / "units" / "unit-1.json", run_dir / "events.jsonl"
            state_paths = (contract_path, run_path, unit_path, events_path)
            before = tuple(path.read_bytes() for path in state_paths)
            original_write_text = Path.write_text

            def fail_events(path: Path, *args: object, **kwargs: object) -> int:
                if path == events_path:
                    raise OSError("injected event write")
                return original_write_text(path, *args, **kwargs)

            with patch.object(Path, "write_text", new=fail_events):
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.transition(self.transition_args("unit-1", "implementing"))
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertNotIn("injected event write", str(raised.exception))
            self.assertEqual(tuple(path.read_bytes() for path in state_paths), before)
