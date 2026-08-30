try:
    from .test_statekit_base import *
except ImportError:
    from test_statekit_base import *

class StateFixtureMixin06:
        def init_request_run(self, goal_id: str = "request-goal") -> Path:
            request = self.workspace / f"{goal_id}.md"
            request.write_text(
                "---\ntitle: Direct request\nstatus: request\nconfirmed_at: 2026-08-30T00:00:00Z\n---\n",
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()):
                hwahap_state.init_run(Namespace(
                    workspace=str(self.workspace), goal_id=goal_id, request=str(request)))
            return self.workspace / ".hwahap" / "runs" / goal_id

        def request_lock_args(self, goal_id: str = "request-goal") -> Namespace:
            return Namespace(workspace=str(self.workspace), run_id=goal_id, actor="sol-1",
                             reason="lock request contract", evidence_ref=["test"])

        def _fill_request_contract(self, run_dir: Path) -> None:
            path = run_dir / "contract.json"
            contract = json.loads(path.read_text())
            for field in hwahap_state.CONTRACT_LISTS:
                contract[field] = ["src" if field == "allowed_paths" else "test" if field == "test_commands" else "entry"]
            self.write_json(path, contract)

        def prepare_locked_run_for_add_unit(self) -> Path:
            run_dir = self.init_run()
            contract_path = run_dir / "contract.json"
            contract = json.loads(contract_path.read_text())
            for field in hwahap_state.CONTRACT_LISTS:
                contract[field] = ["src" if field == "allowed_paths" else "test" if field == "test_commands" else "entry"]
            self.write_json(contract_path, contract)
            self.bind_goal()
            with redirect_stdout(io.StringIO()):
                hwahap_state.lock_contract(Namespace(
                    workspace=str(self.workspace), run_id="test-goal", actor="sol-1",
                    reason="approved contract", evidence_ref=["spec.md"],
                ))
            return run_dir

        def prepare_pending_improvement_run(self) -> Path:
            run_dir = self.prepare_reviewing_test_unit()
            unit_path = run_dir / "units" / "unit-1.json"
            unit = json.loads(unit_path.read_text())
            unit["review_history"] = [self.review_round(1, "fail")]
            self.write_json(unit_path, unit)
            self.validate()
            return run_dir

        def prepare_locked_planned_unit(self) -> Path:
            run_dir = self.init_run()
            self.lock_contract(run_dir)
            unit = self.passed_unit()
            unit.update({"status": "planned", "review_history": [], "test_receipts": []})
            self.write_json(run_dir / "units" / "unit-1.json", unit)
            self.write_events(run_dir, [("run", "initialized", "contract_locked")])
            return run_dir
