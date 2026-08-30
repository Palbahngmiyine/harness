try:
    from .test_statekit_base import *
except ImportError:
    from test_statekit_base import *

class StateFixtureMixin02:
        def lock_contract(self, run_dir: Path) -> dict:
            path = run_dir / "contract.json"
            contract = json.loads(path.read_text())
            for field in hwahap_state.CONTRACT_LISTS:
                contract[field] = ["src" if field == "allowed_paths" else "test" if field == "test_commands" else "entry"]
            contract["locked"] = True
            contract["lock_sha256"] = hwahap_state.canonical_contract_digest(contract)
            self.write_json(path, contract)
            return contract

        def transition_args(self, entity: str, target: str, **overrides: object) -> Namespace:
            values = {
                "workspace": str(self.workspace), "run_id": "test-goal", "entity": entity,
                "to": target, "actor": "sol-1", "role": "orchestrator",
                "reason": "test transition", "input_digest": "sha256:" + "a" * 64,
                "evidence_ref": ["test"], "review_round": 0, "failure_code": None,
                "failure_reason": None, "failure_evidence": None, "failure_recovery": None,
            }
            values.update(overrides)
            return Namespace(**values)

        def goal_args(self, mode: str, **overrides: object) -> Namespace:
            values = {
                "workspace": str(self.workspace), "run_id": "test-goal", "mode": mode,
                "thread_id": None, "objective_sha256": None, "receipt_sha256": None,
                "reason": "observed Goal state", "evidence_ref": ["goal receipt"],
            }
            values.update(overrides)
            return Namespace(**values)

        @staticmethod
        def bound_goal_link() -> dict:
            record = {
                "mode": "bound", "source": "codex.get_goal", "thread_id": "goal-thread",
                "external_status": "active", "objective_sha256": "sha256:" + "a" * 64,
                "receipt_sha256": "sha256:" + "b" * 64, "reason": "observed Goal state",
                "evidence": ["goal receipt"], "observed_at": "2026-08-27T00:00:00Z",
                "completion_sync": "pending", "sync_result": None, "token_total": None,
            }
            return {"current": copy.deepcopy(record), "history": [record]}

        def assert_invalid(self, message: str = "") -> None:
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                self.validate()
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            if message:
                self.assertIn(message, str(raised.exception))

        def assert_invalid_at(self, workspace: Path, message: str = "") -> None:
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                self.validate_at(workspace)
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            if message:
                self.assertIn(message, str(raised.exception))
