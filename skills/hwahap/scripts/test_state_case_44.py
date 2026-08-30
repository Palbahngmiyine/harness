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
        def test_next_unit_waits_for_review_gate_and_overlap_is_invalid(self) -> None:
            run_dir = self.prepare_test_unit()
            run_path = run_dir / "run.json"
            unit_one_path = run_dir / "units" / "unit-1.json"
            unit_two_path = run_dir / "units" / "unit-2.json"
            unit_one = json.loads(unit_one_path.read_text())
            unit_two = copy.deepcopy(unit_one)
            unit_one["status"] = "reviewing"
            unit_two.update({"unit_id": "unit-2", "status": "planned", "review_history": [], "test_receipts": []})
            run = json.loads(run_path.read_text())
            run["status"] = "reviewing"
            run["metrics"]["unit_count"] = 2
            self.write_json(run_path, run)
            self.write_json(unit_one_path, unit_one)
            self.write_json(unit_two_path, unit_two)
            self.write_events(run_dir, [
                ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
                ("unit-1", "planned", "implementing"), ("run", "implementing", "reviewing"),
                ("unit-1", "implementing", "reviewing"),
            ])
            self.validate()
            before = {path: path.read_bytes() for path in (run_path, unit_one_path, unit_two_path, run_dir / "events.jsonl")}
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.transition(self.transition_args("unit-2", "implementing"))
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertIn("only one unit", str(raised.exception))
            self.assertEqual({path: path.read_bytes() for path in before}, before)

            unit_one["status"] = "implementing"
            unit_two["status"] = "reviewing"
            self.write_json(unit_one_path, unit_one)
            self.write_json(unit_two_path, unit_two)
            self.write_events(run_dir, [
                ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
                ("run", "implementing", "reviewing"), ("unit-1", "planned", "implementing"),
                ("unit-2", "planned", "implementing"), ("unit-2", "implementing", "reviewing"),
            ])
            self.assert_invalid("only one unit")

            unit_one["status"] = unit_two["status"] = "reviewing"
            self.write_json(unit_one_path, unit_one)
            self.write_json(unit_two_path, unit_two)
            self.write_events(run_dir, [
                ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
                ("run", "implementing", "reviewing"), ("unit-1", "planned", "implementing"),
                ("unit-1", "implementing", "reviewing"), ("unit-2", "planned", "implementing"),
                ("unit-2", "implementing", "reviewing"),
            ])
            self.assert_invalid("only one unit")

        def test_final_review_freezes_unit_transition(self) -> None:
            run_dir = self.prepare_final_review()
            unit_path, events_path = run_dir / "units" / "unit-1.json", run_dir / "events.jsonl"
            before = unit_path.read_bytes(), events_path.read_bytes()
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.transition(self.transition_args("unit-1", "reviewing"))
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertIn("unit mutation is forbidden", str(raised.exception))
            self.assertEqual((unit_path.read_bytes(), events_path.read_bytes()), before)

        def test_final_review_requires_at_least_one_unit(self) -> None:
            run_dir = self.prepare_final_review()
            (run_dir / "units" / "unit-1.json").unlink()
            self.assert_invalid("final_review requires at least one passed unit")

        def test_final_review_rejects_nonpassed_unit(self) -> None:
            run_dir = self.prepare_final_review()
            unit_path = run_dir / "units" / "unit-1.json"
            unit = json.loads(unit_path.read_text())
            unit["status"] = "reviewing"
            self.write_json(unit_path, unit)
            self.write_events(run_dir, [
                ("unit-1", "planned", "implementing"), ("unit-1", "implementing", "reviewing"),
                ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
                ("run", "implementing", "reviewing"), ("run", "reviewing", "final_review"),
            ])
            self.assert_invalid("final_review requires a passed unit")
