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
        def test_single_writer_rejects_second_activation_and_hand_edited_cardinality(self) -> None:
            run_dir = self.prepare_test_unit()
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            run["status"] = "implementing"
            self.write_json(run_path, run)
            unit_two = copy.deepcopy(json.loads((run_dir / "units" / "unit-1.json").read_text()))
            unit_two.update({"unit_id": "unit-2", "status": "planned", "review_history": [], "test_receipts": []})
            self.write_json(run_dir / "units" / "unit-2.json", unit_two)
            self.write_events(run_dir, [
                ("run", "initialized", "contract_locked"),
                ("run", "contract_locked", "implementing"), ("unit-1", "planned", "implementing"),
            ])
            # A planned -> implementing command must fail before either state or the event log changes.
            before = {path: path.read_bytes() for path in (
                run_dir / "run.json", run_dir / "units" / "unit-1.json",
                run_dir / "units" / "unit-2.json", run_dir / "events.jsonl")}
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.transition(self.transition_args("unit-2", "implementing"))
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertIn("only one unit", str(raised.exception))
            self.assertEqual({path: path.read_bytes() for path in before}, before)

            # A hand-edited second active unit and matching event must also fail validation.
            unit_two["status"] = "implementing"
            self.write_json(run_dir / "units" / "unit-2.json", unit_two)
            self.write_events(run_dir, [
                ("run", "initialized", "contract_locked"),
                ("run", "contract_locked", "implementing"),
                ("unit-1", "planned", "implementing"), ("unit-2", "planned", "implementing"),
            ])
            self.assert_invalid("only one unit")
