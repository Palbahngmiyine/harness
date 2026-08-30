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
        def test_unresolved_unit_blocks_new_unit_but_allows_same_unit_resume(self) -> None:
            run_dir = self.prepare_test_unit()
            run_path = run_dir / "run.json"
            unit_one_path = run_dir / "units" / "unit-1.json"
            unit_two_path = run_dir / "units" / "unit-2.json"
            unit_one = json.loads(unit_one_path.read_text())
            unit_one["status"] = "recovery"
            unit_one["review_history"] = [self.review_round(1, "fail")]
            unit_one["improvement_history"] = [self.improvement_record(1, "terra_recovery")]
            unit_two = copy.deepcopy(unit_one)
            unit_two.update({"unit_id": "unit-2", "status": "planned", "review_history": [],
                             "improvement_history": [], "replan_count": 0})
            run = json.loads(run_path.read_text())
            run["status"] = "recovering"
            run["metrics"]["unit_count"] = 2
            self.write_json(run_path, run)
            self.write_json(unit_one_path, unit_one)
            self.write_json(unit_two_path, unit_two)
            self.write_events(run_dir, [
                ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
                ("unit-1", "planned", "implementing"), ("run", "implementing", "reviewing"),
                ("unit-1", "implementing", "reviewing"), ("run", "reviewing", "recovering"),
                ("unit-1", "reviewing", "recovery"),
            ])
            self.validate()
            state_paths = (run_path, unit_one_path, unit_two_path, run_dir / "events.jsonl")
            before = tuple(path.read_bytes() for path in state_paths)
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.transition(self.transition_args("unit-2", "implementing"))
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertEqual(tuple(path.read_bytes() for path in state_paths), before)
            with redirect_stdout(io.StringIO()):
                hwahap_state.transition(self.transition_args("run", "implementing"))
                hwahap_state.transition(self.transition_args("unit-1", "implementing"))
            self.validate()

            passed = self.passed_unit()
            command = unit_one["acceptance_commands"][0]
            passed["acceptance_commands"] = [command]
            passed["test_receipts"][0]["command_sha256"] = "sha256:" + hashlib.sha256(command.encode()).hexdigest()
            run["status"] = "reviewing"
            self.write_json(run_path, run)
            self.write_json(unit_one_path, passed)
            self.write_events(run_dir, self.phase_events("passed"))
            self.validate()
            with redirect_stdout(io.StringIO()):
                hwahap_state.transition(self.transition_args("run", "implementing"))
                hwahap_state.transition(self.transition_args("unit-2", "implementing"))
            self.validate()
