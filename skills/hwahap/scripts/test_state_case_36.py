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
        def test_recursive_improvement_history_allows_recovery_and_rejects_reuse(self) -> None:
            run_dir = self.init_run()
            run_path = run_dir / "run.json"
            unit_path = run_dir / "units" / "unit-1.json"
            cases = (
                (["fail", "pass"], "passed", 0, ["terra_recovery", ""]),
                (["fail", "fail", "pass"], "passed", 1, ["terra_recovery", "sol_replan", ""]),
                (["fail", "fail", "fail", "pass"], "passed", 2, ["terra_recovery", "sol_replan", "recursive_improvement", ""]),
                (["fail", "fail", "fail", "fail", "pass"], "passed", 3, ["terra_recovery", "sol_replan", "recursive_improvement", "recursive_improvement", ""]),
                (["fail"], "recovery", 0, ["terra_recovery"]),
                (["fail", "fail"], "recovery", 1, ["terra_recovery", "sol_replan"]),
                (["fail"], "awaiting_user", 0, []),
                (["fail"], "reviewing", 0, ["terra_recovery"]),
                (["fail", "pass", "fail"], "replan_required", 1, ["terra_recovery", "sol_replan"]),
            )
            for outcomes, status, replan_count, kinds in cases:
                with self.subTest(outcomes=outcomes, status=status):
                    unit = self.passed_unit()
                    unit["status"] = status
                    unit["review_history"] = [self.review_round(index, outcome) for index, outcome in enumerate(outcomes, 1)]
                    unit["replan_count"] = replan_count
                    unit["improvement_history"] = [
                        self.improvement_record(index, kind) for index, kind in enumerate(kinds, 1) if kind
                    ]
                    if status == "passed":
                        final_review = unit["review_history"][-1]
                        unit["test_receipts"][0]["observer_thread_id"] = final_review["verifier"]["thread_id"]
                        unit["test_receipts"][0]["diff_digest"] = final_review["diff_digest"]
                    if status == "awaiting_user":
                        unit["failure"] = {
                            "code": "HW_USER_DECISION_REQUIRED", "reason": "need user decision",
                            "evidence": ["review"], "recovery": "ask user",
                        }
                    run = json.loads(run_path.read_text())
                    run["status"] = {
                        "recovery": "recovering", "replan_required": "replanning",
                        "passed": "reviewing", "reviewing": "reviewing", "awaiting_user": "reviewing",
                    }[status]
                    run["metrics"]["unit_count"] = 1
                    self.write_json(run_path, run)
                    self.write_json(unit_path, unit)
                    transitions = self.phase_events(status, run["status"])
                    self.write_events(run_dir, transitions)
                    if status in {"reviewing", "recovery"} and outcomes == ["fail", "fail"]:
                        self.assert_invalid("recovery requires")
                    elif status == "reviewing" and outcomes == ["fail"] and kinds == ["terra_recovery"]:
                        self.validate()
                    elif status == "reviewing":
                        self.assert_invalid("reviewing cannot end")
                    elif status == "replan_required" and outcomes == ["fail", "pass", "fail"]:
                        self.assert_invalid("failed review cannot follow")
                    else:
                        self.validate()

            duplicate = self.passed_unit()
            duplicate["review_history"] = [self.review_round(1, "fail"), self.review_round(2, "pass")]
            duplicate["improvement_history"] = [self.improvement_record(1, "terra_recovery")] * 2
            self.write_json(unit_path, duplicate)
            run = json.loads(run_path.read_text())
            run["status"] = "reviewing"
            self.write_json(run_path, run)
            self.write_events(run_dir, [
                ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
                ("unit-1", "planned", "implementing"), ("run", "implementing", "reviewing"),
                ("unit-1", "implementing", "reviewing"),
                ("unit-1", "reviewing", "passed"),
            ])
            self.assert_invalid("reused")
