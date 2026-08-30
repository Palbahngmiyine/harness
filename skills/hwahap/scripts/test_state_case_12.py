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
        def test_terminal_run_rejects_unit_successor_in_event_history(self) -> None:
            run_dir = self.init_run()
            self.lock_contract(run_dir)
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            run.update({"status": "blocked", "failure": {
                "code": "HW_IMPLEMENTATION_BLOCKED", "reason": "stop",
                "evidence": ["test"], "recovery": "retry"}})
            self.write_json(run_path, run)
            self.write_json(run_dir / "units" / "unit-1.json", {
                "unit_id": "unit-1", "status": "implementing", "writer": "hwahap-luna-implementer",
                "allowed_paths": ["src"], "acceptance_commands": ["test"], "test_receipts": [],
                "replan_count": 0, "review_history": [], "improvement_history": [],
                "recovery": None, "failure": None,
            })
            self.write_events(run_dir, [
                ("run", "initialized", "contract_locked"), ("run", "contract_locked", "blocked"),
                ("unit-1", "planned", "implementing"),
            ])
            self.assert_invalid("terminal run cannot have unit successors")

        def test_final_review_transition_requires_ready_passed_units_and_preserves_state(self) -> None:
            run_dir = self.init_run()
            contract = self.lock_contract(run_dir)
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            run["status"] = "reviewing"
            self.write_json(run_path, run)
            self.write_events(run_dir, [
                ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
                ("run", "implementing", "reviewing"),
            ])
            before = {name: (run_dir / name).read_bytes() for name in ("run.json", "events.jsonl")}
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.transition(self.transition_args("run", "final_review"))
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertEqual(before, {name: (run_dir / name).read_bytes() for name in before})

            unit = self.passed_unit()
            self.write_json(run_dir / "units" / "unit-1.json", unit)
            run["metrics"]["unit_count"] = 1
            self.write_json(run_path, run)
            self.write_events(run_dir, self.phase_events("passed"))
            self.validate()
            with redirect_stdout(io.StringIO()):
                hwahap_state.transition(self.transition_args("run", "final_review"))
            self.validate()
            self.assertEqual(json.loads(run_path.read_text())["status"], "final_review")

        def test_complete_generation_failure_rolls_back_without_report(self) -> None:
            run_dir = self.prepare_final_review()
            before = {name: (run_dir / name).read_bytes() for name in ("run.json", "events.jsonl")}
            original = hwahap_state.report_module
            class BrokenReport:
                def build_payload(self, *args): return {}
                def canonical_payload_digest(self, payload): return "sha256:" + "b" * 64
                def render_report(self, *args): raise ValueError("forced report failure")
            hwahap_state.report_module = lambda: BrokenReport()
            try:
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.complete_run(self.complete_args())
            finally:
                hwahap_state.report_module = original
            self.assertEqual(raised.exception.code, "HW_REPORT_GENERATION_FAILED")
            self.assertEqual(before, {name: (run_dir / name).read_bytes() for name in before})
            self.assertFalse((run_dir / "report.html").exists())
