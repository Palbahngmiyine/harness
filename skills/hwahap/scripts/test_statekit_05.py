try:
    from .test_statekit_base import *
except ImportError:
    from test_statekit_base import *

class StateFixtureMixin05:
        def prepare_test_unit(self, command: str = "python3 -c \"print('runtime' + '-canary')\"") -> Path:
            run_dir = self.init_run()
            contract = self.lock_contract(run_dir)
            contract["test_commands"] = [command]
            contract["lock_sha256"] = hwahap_state.canonical_contract_digest(contract)
            self.write_json(run_dir / "contract.json", contract)
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            run["status"] = "contract_locked"
            self.write_json(run_path, run)
            self.write_events(run_dir, [("run", "initialized", "contract_locked"), ("unit-1", "planned", "implementing")])
            unit = self.passed_unit()
            unit.update({"title": "test unit", "status": "implementing", "review_history": [], "test_receipts": []})
            unit["acceptance_commands"] = [command]
            self.write_json(run_dir / "units" / "unit-1.json", unit)
            run["metrics"]["unit_count"] = 1
            self.write_json(run_path, run)
            return run_dir

        def prepare_reviewing_test_unit(self, command: str = "test") -> Path:
            run_dir = self.prepare_test_unit(command)
            run_path, unit_path = run_dir / "run.json", run_dir / "units" / "unit-1.json"
            run = json.loads(run_path.read_text())
            unit = json.loads(unit_path.read_text())
            run["status"], unit["status"] = "reviewing", "reviewing"
            self.write_json(run_path, run)
            self.write_json(unit_path, unit)
            self.write_events(run_dir, self.phase_events())
            self.validate()
            return run_dir

        def run_test_args(self, **overrides: object) -> Namespace:
            values = {"workspace": str(self.workspace), "run_id": "test-goal", "unit_id": "unit-1",
                      "command_index": 1, "timeout_seconds": 5}
            values.update(overrides)
            return Namespace(**values)

        def record_receipt_args(self, **overrides: object) -> Namespace:
            values = {
                "workspace": str(self.workspace), "run_id": "test-goal", "unit_id": "unit-1",
                "command_index": 1, "execution_receipt_sha256": "sha256:" + "d" * 64,
                "observer_thread_id": "verifier-thread", "diff_digest": self.snapshot["diff_digest"],
                "base_commit": self.base_commit, "target_commit": self.target_commit,
                "started_at": "2026-08-27T00:00:00Z", "ended_at": "2026-08-27T00:00:01Z",
                "output_sha256": "sha256:" + "f" * 64, "exit_code": 0, "timed_out": False,
            }
            values.update(overrides)
            return Namespace(**values)

        def goal_complete_args(self, result: str = "completed") -> Namespace:
            return Namespace(workspace=str(self.workspace), run_id="test-goal", sync_result=result,
                             receipt_sha256="sha256:" + "c" * 64, reason="Goal completion observed",
                             evidence_ref=["goal-update"], token_total=None if result == "failed" else 123)

        def review_round(self, number: int, outcome: str = "fail") -> dict:
            digest = self.snapshot["diff_digest"]
            return {
                "round": number, "diff_snapshot": copy.deepcopy(self.snapshot), "diff_digest": digest,
                "changed_paths": ["src"], "outcome": outcome,
                "verifier": {"model": "gpt-5.6-luna", "effort": "xhigh", "status": outcome, "thread_id": f"luna-{number}", "diff_digest": digest, "evidence": ["verify"]},
                "scope_reviewer": {"model": "gpt-5.6-terra", "effort": "xhigh", "status": outcome, "thread_id": f"terra-{number}", "diff_digest": digest, "evidence": ["scope"]},
            }

        @staticmethod
        def improvement_record(number: int, kind: str) -> dict:
            return {
                "after_round": number, "kind": kind,
                "failure_signature": "sha256:" + str(number) * 64,
                "root_cause": "failure", "hypothesis": "new strategy", "action": "apply strategy",
                "strategy_digest": "sha256:" + chr(96 + number) * 64,
                "scope_status": "within_contract", "evidence": [f"round-{number}"],
            }
