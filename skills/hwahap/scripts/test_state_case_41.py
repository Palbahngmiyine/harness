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
        def test_validate_events_rejects_unit_phase_before_run_phase(self) -> None:
            for index, (run_status, unit_status, transitions) in enumerate((
                ("implementing", "implementing", [
                    ("run", "initialized", "contract_locked"),
                    ("unit-1", "planned", "implementing"),
                    ("run", "contract_locked", "implementing"),
                ]),
                ("reviewing", "reviewing", [
                    ("run", "initialized", "contract_locked"),
                    ("run", "contract_locked", "implementing"),
                    ("unit-1", "planned", "implementing"),
                    ("unit-1", "implementing", "reviewing"),
                    ("run", "implementing", "reviewing"),
                ]),
            )):
                run_dir = self.init_run(f"phase-{index}")
                self.lock_contract(run_dir)
                run_path = run_dir / "run.json"
                run = json.loads(run_path.read_text())
                run["status"] = run_status
                run["metrics"]["unit_count"] = 1
                unit = self.passed_unit()
                unit["status"] = unit_status
                self.write_json(run_path, run)
                self.write_json(run_dir / "units" / "unit-1.json", unit)
                self.write_events(run_dir, transitions)
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    self.validate_at(self.workspace, f"phase-{index}")
                self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                self.assertIn("unit transition requires run status", str(raised.exception))

        def test_recovery_and_replan_can_resume_implementing_and_history_is_required(self) -> None:
            run_dir = self.init_run()
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            run["status"] = "recovering"
            self.write_json(run_path, run)
            unit_path = run_dir / "units" / "unit-1.json"
            unit = self.passed_unit()
            unit["status"] = "recovery"
            unit["review_history"] = [self.review_round(1, "fail")]
            unit["improvement_history"] = [self.improvement_record(1, "terra_recovery")]
            self.write_json(unit_path, unit)
            self.write_events(run_dir, self.phase_events("recovery", "recovering"))
            self.validate()
            with redirect_stdout(io.StringIO()):
                hwahap_state.transition(self.transition_args("run", "implementing"))
                hwahap_state.transition(self.transition_args("unit-1", "implementing"))
            self.validate()

            unit["status"] = "implementing"
            unit["improvement_history"] = []
            self.write_json(unit_path, unit)
            self.assert_invalid("requires improvement")

            unit["status"] = "replan_required"
            unit["review_history"] = [self.review_round(1, "fail"), self.review_round(2, "fail")]
            unit["improvement_history"] = [
                self.improvement_record(1, "terra_recovery"), self.improvement_record(2, "sol_replan")
            ]
            unit["replan_count"] = 1
            unit["failure"] = {
                "code": "HW_REPLAN_REQUIRED", "reason": "replan", "evidence": ["review"], "recovery": "retry",
            }
            self.write_json(unit_path, unit)
            run["status"] = "replanning"
            self.write_json(run_path, run)
            self.write_events(run_dir, [
                ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
                ("unit-1", "planned", "implementing"), ("run", "implementing", "reviewing"),
                ("unit-1", "implementing", "reviewing"), ("run", "reviewing", "recovering"),
                ("unit-1", "reviewing", "recovery"), ("run", "recovering", "implementing"),
                ("unit-1", "recovery", "implementing"), ("run", "implementing", "reviewing"),
                ("unit-1", "implementing", "reviewing"), ("run", "reviewing", "replanning"),
                ("unit-1", "reviewing", "replan_required"),
            ])
            self.validate()
            with redirect_stdout(io.StringIO()):
                hwahap_state.transition(self.transition_args("run", "implementing"))
                hwahap_state.transition(self.transition_args("unit-1", "implementing"))
            self.validate()
