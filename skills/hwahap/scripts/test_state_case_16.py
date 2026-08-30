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
        def test_completed_lifecycle_persists_101_valid_improvement_candidates(self) -> None:
            run_dir = self.prepare_final_review()
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            candidates = [{
                "status": "proposed", "summary": f"candidate-{index}",
                "evidence": [f"candidate-evidence-{index}"],
                "expected_effect": f"candidate-effect-{index}",
                "next_action": f"candidate-action-{index}",
            } for index in range(1, 102)]
            run["improvement_candidates"] = candidates
            self.write_json(run_path, run)
            self.validate()
            with redirect_stdout(io.StringIO()):
                hwahap_state.complete_run(self.complete_args())
            data_path, report_path = run_dir / "report-data.json", run_dir / "report.html"
            receipt = json.loads(run_path.read_text())["report"]
            data = data_path.read_bytes()
            html = report_path.read_bytes()
            self.assertTrue(data_path.is_file() and not data_path.is_symlink() and data_path.stat().st_nlink == 1)
            self.assertTrue(report_path.is_file() and not report_path.is_symlink() and report_path.stat().st_nlink == 1)
            self.assertEqual(receipt["source_payload_sha256"], "sha256:" + hashlib.sha256(data).hexdigest())
            self.assertEqual(receipt["data"]["file_sha256"], "sha256:" + hashlib.sha256(data).hexdigest())
            self.assertEqual(receipt["html"]["file_sha256"], "sha256:" + hashlib.sha256(html).hexdigest())
            parsed = json.loads(data)
            self.assertEqual(parsed["improvement-candidates"], candidates)
            html_text = html.decode("utf-8")
            for index, summary in ((0, "candidate-1"), (100, "candidate-101")):
                row = (f'<tr><td>/improvement-candidates/{index}/summary</td><td>string</td>'
                       f'<td>&quot;{summary}&quot;</td></tr>')
                self.assertEqual(html_text.count(row), 1)
            self.validate()

        def test_goal_complete_sync_success_updates_provenance_without_event(self) -> None:
            run_dir = self.prepare_final_review()
            with redirect_stdout(io.StringIO()):
                hwahap_state.complete_run(self.complete_args())
            events_before = (run_dir / "events.jsonl").read_bytes()
            report_before = (run_dir / "report.html").read_bytes()
            with redirect_stdout(io.StringIO()):
                hwahap_state.goal_complete_sync(self.goal_complete_args())
            run = json.loads((run_dir / "run.json").read_text())
            current = run["goal_link"]["current"]
            self.assertEqual(current["source"], "codex.update_goal")
            self.assertEqual(current["external_status"], "completed")
            self.assertEqual(current["completion_sync"], "completed")
            self.assertEqual(current["sync_result"], "completed")
            self.assertEqual(len(run["goal_link"]["history"]), 2)
            self.assertEqual(run["metrics"]["token_usage"], {
                "availability": "available", "source": "codex.update_goal", "total": 123, "reason": None})
            self.assertEqual((run_dir / "events.jsonl").read_bytes(), events_before)
            self.assertNotEqual((run_dir / "report.html").read_bytes(), report_before)
            self.assertIn(b"Goal sync result", (run_dir / "report.html").read_bytes())
            self.validate()

        def test_goal_complete_sync_failure_is_not_local_goal_completion(self) -> None:
            run_dir = self.prepare_final_review()
            before_token = json.loads((run_dir / "run.json").read_text())["metrics"]["token_usage"]
            with redirect_stdout(io.StringIO()):
                hwahap_state.complete_run(self.complete_args())
            bad = self.goal_complete_args("failed")
            bad.token_total = 1
            with self.assertRaises(hwahap_state.HwahapError):
                hwahap_state.goal_complete_sync(bad)
            with redirect_stdout(io.StringIO()):
                hwahap_state.goal_complete_sync(self.goal_complete_args("failed"))
            current = json.loads((run_dir / "run.json").read_text())["goal_link"]["current"]
            self.assertEqual(current["external_status"], "active")
            self.assertEqual(current["completion_sync"], "failed")
            self.assertEqual(current["sync_result"], "failed")
            self.assertEqual(json.loads((run_dir / "run.json").read_text())["metrics"]["token_usage"], before_token)
            self.validate()
