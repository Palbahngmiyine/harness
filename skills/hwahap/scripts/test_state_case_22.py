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
        def test_completed_run_requires_observed_goal_but_allows_bound_pending(self) -> None:
            run_dir = self.init_run()
            unobserved = json.loads((run_dir / "run.json").read_text())["goal_link"]
            contract = self.lock_contract(run_dir)
            unit = self.passed_unit()
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            run.update({
                "status": "final_review", "completed_at": None,
                "metrics": {**run["metrics"], "unit_count": 1, "review_rounds": 1},
            })
            run["goal_link"] = unobserved
            self.write_json(run_dir / "contract.json", contract)
            self.write_json(run_path, run)
            self.write_json(run_dir / "units" / "unit-1.json", unit)
            transitions = self.phase_events("passed") + [("run", "reviewing", "final_review")]
            self.write_events(run_dir, transitions)
            run["status"] = "completed"
            run["completed_at"] = "2026-08-27T00:00:00Z"
            run["final_review"] = {"status": "pass", "attempts": [{
                "model": "gpt-5.6-sol", "effort": "ultra", "status": "pass",
                "thread_id": "final-1", "evidence": ["review"], "diff_snapshot": copy.deepcopy(self.snapshot),
                "diff_digest": self.snapshot["diff_digest"],
            }]}
            self.write_json(run_path, run)
            self.write_events(run_dir, transitions + [("run", "final_review", "completed")])
            self.bind_last_event_digest(run_dir)
            self.assert_invalid("bound Goal")
            run["status"] = "final_review"
            run["completed_at"] = None
            run["final_review"] = {"status": "pending", "attempts": []}
            run["goal_link"] = self.bound_goal_link()
            self.write_json(run_path, run)
            self.write_events(run_dir, transitions)
            run = json.loads(run_path.read_text())
            run["status"] = "completed"
            run["completed_at"] = "2026-08-27T00:00:00Z"
            run["final_review"] = {"status": "pass", "attempts": [{
                "model": "gpt-5.6-sol", "effort": "ultra", "status": "pass",
                "thread_id": "final-1", "evidence": ["review"], "diff_snapshot": copy.deepcopy(self.snapshot),
                "diff_digest": self.snapshot["diff_digest"],
            }]}
            self.write_json(run_path, run)
            self.write_events(run_dir, transitions + [("run", "final_review", "completed")])
            self.bind_last_event_digest(run_dir)
            self.write_report_receipt(run_dir)
            self.validate()

        def test_same_spec_init_is_idempotent(self) -> None:
            run_dir = self.init_run()
            before = {name: (run_dir / name).read_bytes() for name in ("contract.json", "run.json")}
            self.init_run()
            after = {name: (run_dir / name).read_bytes() for name in before}
            self.assertEqual(before, after)

        def test_request_init_validate_and_reinit_are_idempotent(self) -> None:
            run_dir = self.init_request_run()
            self.validate_at(self.workspace, "request-goal")
            before = {name: (run_dir / name).read_bytes() for name in ("contract.json", "run.json")}
            request = self.workspace / "request-goal.md"
            with redirect_stdout(io.StringIO()):
                hwahap_state.init_run(Namespace(
                    workspace=str(self.workspace), goal_id="request-goal", request=str(request)))
            self.assertEqual(before, {name: (run_dir / name).read_bytes() for name in before})
            self.assertEqual(json.loads((run_dir / "contract.json").read_text())["spec"]["status"], "request")

        def test_request_wrong_status_is_rejected_with_request_code(self) -> None:
            request = self.workspace / "wrong-request.md"
            request.write_text(
                "---\ntitle: Direct request\nstatus: prfaq\nconfirmed_at: 2026-08-30T00:00:00Z\n---\n",
                encoding="utf-8",
            )
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.init_run(Namespace(
                    workspace=str(self.workspace), goal_id="wrong-request", request=str(request)))
            self.assertEqual(raised.exception.code, "HW_REQUEST_UNCONFIRMED")
            self.assertFalse((self.workspace / ".hwahap" / "runs" / "wrong-request").exists())
