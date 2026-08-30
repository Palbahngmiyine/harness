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
        def test_goal_complete_sync_already_completed_and_invalid_result(self) -> None:
            run_dir = self.prepare_final_review()
            with redirect_stdout(io.StringIO()):
                hwahap_state.complete_run(self.complete_args())
                hwahap_state.goal_complete_sync(self.goal_complete_args("already_completed"))
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            self.assertEqual(run["goal_link"]["current"]["sync_result"], "already_completed")
            self.assertIn("already_completed", (run_dir / "report.html").read_text())
            run["goal_link"]["current"]["sync_result"] = "bogus"
            run["goal_link"]["history"][-1]["sync_result"] = "bogus"
            self.write_json(run_path, run)
            self.assert_invalid("sync_result")
            run["goal_link"]["current"].update({"sync_result": "failed", "completion_sync": "completed", "external_status": "completed"})
            run["goal_link"]["history"][-1] = copy.deepcopy(run["goal_link"]["current"])
            self.write_json(run_path, run)
            self.assert_invalid("completion Goal receipt")

        def test_goal_history_rejects_changed_bound_pair_and_update_first(self) -> None:
            run_dir = self.init_run()
            with redirect_stdout(io.StringIO()):
                hwahap_state.goal_sync(self.goal_args("bound", thread_id="goal-thread", objective_sha256="sha256:" + "a" * 64, receipt_sha256="sha256:" + "b" * 64))
                hwahap_state.goal_sync(self.goal_args("bound", thread_id="goal-thread", objective_sha256="sha256:" + "a" * 64, receipt_sha256="sha256:" + "c" * 64))
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            run["goal_link"]["history"][0]["thread_id"] = "other-thread"
            self.write_json(run_path, run)
            self.assert_invalid("bound thread/objective")
            record = copy.deepcopy(run["goal_link"]["current"])
            record.update({"source": "codex.update_goal", "completion_sync": "failed", "sync_result": "failed", "external_status": "active"})
            run["goal_link"] = {"current": record, "history": [record]}
            self.write_json(run_path, run)
            self.assert_invalid("prior get_goal")

        def test_goal_complete_sync_rejects_wrong_state_or_tampered_report(self) -> None:
            run_dir = self.prepare_final_review()
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.goal_complete_sync(self.goal_complete_args())
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            with redirect_stdout(io.StringIO()):
                hwahap_state.complete_run(self.complete_args())
            report_path = run_dir / "report.html"
            report_path.write_bytes(report_path.read_bytes() + b"tamper")
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.goal_complete_sync(self.goal_complete_args())
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")

        def test_goal_complete_sync_rolls_back_run_and_report_on_generation_failure(self) -> None:
            run_dir = self.prepare_final_review()
            with redirect_stdout(io.StringIO()):
                hwahap_state.complete_run(self.complete_args())
            run_before = (run_dir / "run.json").read_bytes()
            report_before = (run_dir / "report.html").read_bytes()
            events_before = (run_dir / "events.jsonl").read_bytes()
            original = hwahap_state.validate_run
            calls = 0
            def fail_after_write(args: Namespace) -> None:
                nonlocal calls
                calls += 1
                if calls > 1:
                    raise hwahap_state.HwahapError("HW_STATE_INVALID", "/private/tmp/credential-canary forced sync failure")
                original(args)
            hwahap_state.validate_run = fail_after_write
            try:
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.goal_complete_sync(self.goal_complete_args())
            finally:
                hwahap_state.validate_run = original
            self.assertEqual(raised.exception.code, "HW_REPORT_GENERATION_FAILED")
            self.assertEqual(str(raised.exception), "Goal completion report generation failed")
            self.assertNotIn("credential-canary", str(raised.exception))
            self.assertNotIn("/private/tmp", str(raised.exception))
            self.assertEqual((run_dir / "run.json").read_bytes(), run_before)
            self.assertEqual((run_dir / "report.html").read_bytes(), report_before)
            self.assertEqual((run_dir / "events.jsonl").read_bytes(), events_before)
