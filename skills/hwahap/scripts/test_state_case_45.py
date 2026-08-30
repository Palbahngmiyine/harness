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
        def test_completed_metrics_include_recursive_review_history(self) -> None:
            run_dir = self.init_run()
            contract = self.lock_contract(run_dir)
            unit = self.passed_unit()
            unit["review_history"] = [
                self.review_round(1, "fail"), self.review_round(2, "fail"), self.review_round(3, "pass")
            ]
            unit["improvement_history"] = [
                self.improvement_record(1, "terra_recovery"), self.improvement_record(2, "sol_replan")
            ]
            unit["replan_count"] = 1
            unit["test_receipts"][0]["observer_thread_id"] = "luna-3"
            unit["test_receipts"][0]["diff_digest"] = self.snapshot["diff_digest"]
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            run.update({
                "status": "completed", "completed_at": "2026-08-27T00:00:00Z",
                "final_review": {"status": "pass", "attempts": [{
                    "model": "gpt-5.6-sol", "effort": "ultra", "status": "pass",
                    "thread_id": "final-1", "evidence": ["review"], "diff_snapshot": copy.deepcopy(self.snapshot),
                    "diff_digest": self.snapshot["diff_digest"],
                }]},
            })
            run["goal_link"] = self.bound_goal_link()
            run["metrics"].update({
                "unit_count": 1, "review_rounds": 3, "recoveries": 1, "replans": 1,
                "scope_deviations": 0,
            })
            self.write_json(run_dir / "contract.json", contract)
            self.write_json(run_path, run)
            self.write_json(run_dir / "units" / "unit-1.json", unit)
            self.write_events(run_dir, [
                ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
                ("unit-1", "planned", "implementing"), ("run", "implementing", "reviewing"),
                ("unit-1", "implementing", "reviewing"), ("unit-1", "reviewing", "passed"),
                ("run", "reviewing", "final_review"),
                ("run", "final_review", "completed"),
            ])
            self.bind_last_event_digest(run_dir)
            self.write_report_receipt(run_dir)
            self.validate()

        def test_locked_contract_requires_all_six_lists(self) -> None:
            run_dir = self.init_run()
            base = json.loads((run_dir / "contract.json").read_text())
            for field in hwahap_state.CONTRACT_LISTS:
                with self.subTest(field=field):
                    contract = copy.deepcopy(base)
                    contract["locked"] = True
                    for name in hwahap_state.CONTRACT_LISTS:
                        contract[name] = ["entry"]
                    contract[field] = []
                    self.write_json(run_dir / "contract.json", contract)
                    self.assert_invalid("locked contract fields must be nonempty")
