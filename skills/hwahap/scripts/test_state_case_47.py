try:
    from .test_statekit_base import *
    from .test_statekit_01 import *
    from .test_statekit_02 import *
    from .test_statekit_03 import *
except ImportError:
    from test_statekit_base import *
    from test_statekit_01 import *
    from test_statekit_02 import *
    from test_statekit_03 import *

class HwahapStateTests(StateFixtureMixin01, StateFixtureMixin02, StateFixtureMixin03, unittest.TestCase):
        def test_replan_required_needs_review_round_and_failure_evidence(self) -> None:
            run_dir = self.init_run()
            unit_path = run_dir / "units" / "unit-1.json"
            digest = self.snapshot["diff_digest"]
            def failed_round(round_number: int) -> dict:
                return {
                    "round": round_number, "diff_snapshot": copy.deepcopy(self.snapshot),
                    "diff_digest": digest, "changed_paths": ["src"], "outcome": "fail",
                    "verifier": {"model": "gpt-5.6-luna", "effort": "xhigh", "status": "fail", "thread_id": f"luna-{round_number}", "diff_digest": digest, "evidence": ["verify failed"]},
                    "scope_reviewer": {"model": "gpt-5.6-terra", "effort": "xhigh", "status": "fail", "thread_id": f"terra-{round_number}", "diff_digest": digest, "evidence": ["scope failed"]},
                }
            def improvement(round_number: int, kind: str) -> dict:
                return {
                    "after_round": round_number, "kind": kind,
                    "failure_signature": "sha256:" + str(round_number) * 64,
                    "root_cause": "review failure", "hypothesis": "new strategy helps",
                    "action": "apply bounded recovery", "strategy_digest": "sha256:" + chr(96 + round_number) * 64,
                    "scope_status": "within_contract", "evidence": [f"review-{round_number}"],
                }
            base = {
                "unit_id": "unit-1",
                "title": "observable replan change",
                "status": "replan_required",
                "writer": "hwahap-luna-implementer",
                "allowed_paths": ["src"],
                "acceptance_commands": ["test"],
                "test_receipts": copy.deepcopy(self.passed_unit()["test_receipts"]),
                "replan_count": 1,
                "review_history": [failed_round(1), failed_round(2)],
                "improvement_history": [improvement(1, "terra_recovery"), improvement(2, "sol_replan")],
                "failure": {
                    "code": "HW_REPLAN_REQUIRED",
                    "reason": "scope needs a decision",
                    "evidence": ["review-1"],
                    "recovery": "ask for replanning",
                },
                "recovery": {"reason": "review failed", "evidence": ["review-1"], "action": "retry once"},
            }
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            run["status"] = "replanning"
            self.write_json(run_path, run)
            self.write_json(unit_path, base)
            self.write_events(run_dir, [
                ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
                ("unit-1", "planned", "implementing"), ("run", "implementing", "reviewing"),
                ("unit-1", "implementing", "reviewing"), ("run", "reviewing", "replanning"),
                ("unit-1", "reviewing", "replan_required"),
            ])
            self.validate()
            recovered = copy.deepcopy(base)
            recovered["status"] = "passed"
            recovered["replan_count"] = 1
            recovered["review_history"].append(failed_round(3))
            recovered["review_history"][2]["outcome"] = "pass"
            recovered["review_history"][2]["verifier"]["status"] = "pass"
            recovered["review_history"][2]["scope_reviewer"]["status"] = "pass"
            recovered["test_receipts"][0]["observer_thread_id"] = "luna-3"
            recovered["test_receipts"][0]["diff_digest"] = self.snapshot["diff_digest"]
            recovered["recovery"] = {"reason": "replanned", "evidence": ["review-2"], "action": "retry"}
            self.write_json(unit_path, recovered)
            run["status"] = "reviewing"
            self.write_json(run_path, run)
            self.write_events(run_dir, [
                ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
                ("unit-1", "planned", "implementing"), ("run", "implementing", "reviewing"),
                ("unit-1", "implementing", "reviewing"), ("run", "reviewing", "replanning"),
                ("unit-1", "reviewing", "replan_required"), ("run", "replanning", "implementing"),
                ("unit-1", "replan_required", "implementing"), ("run", "implementing", "reviewing"),
                ("unit-1", "implementing", "reviewing"), ("unit-1", "reviewing", "passed"),
            ])
            self.validate()
            for name, changes, expected in (
                ("review round", {"review_history": [failed_round(1)]}, "two failed rounds"),
                ("evidence", {"failure": {"evidence": []}}, "failure evidence"),
                ("recovery", {"failure": {"recovery": ""}}, "failure evidence"),
            ):
                with self.subTest(case=name):
                    unit = copy.deepcopy(base)
                    if "failure" in changes:
                        unit["failure"].update(changes["failure"])
                    else:
                        unit.update(changes)
                    self.write_json(unit_path, unit)
                    self.assert_invalid(expected)
