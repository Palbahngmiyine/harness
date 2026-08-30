try:
    from .test_terminalkit import *
except ImportError:
    from test_terminalkit import *


class TerminalOutcomeTests(TerminalReportFixture, unittest.TestCase):
    def test_every_non_success_terminal_outcome_generates_valid_report(self):
        for outcome in ("blocked", "failed", "awaiting_user", "cancelled"):
            with self.subTest(outcome=outcome):
                goal_id = "terminal-" + outcome.replace("_", "-")
                run_dir = self.transition_to(goal_id, outcome)
                self.fixture.validate(goal_id)
                run = json.loads((run_dir / "run.json").read_text())
                payload = json.loads((run_dir / "report-data.json").read_text())
                self.assertEqual(run["report"]["status"], "completed")
                self.assertEqual(payload["summary"]["status"], outcome)
                self.assertTrue((run_dir / "report.html").is_file())
                if outcome != "cancelled":
                    self.assertEqual(
                        payload["failures-recovery"][0]["unit_id"], "run")

    def test_terminal_report_failure_rolls_back_all_files(self):
        run_dir = self.fixture.init_run("terminal-rollback")
        run_path, events_path = run_dir / "run.json", run_dir / "events.jsonl"
        before = run_path.read_bytes(), events_path.read_bytes()
        args = self.fixture.transition_args(
            "run", "cancelled", run_id="terminal-rollback")
        with mock.patch.object(
                state, "prepare_report_artifacts", side_effect=ValueError("boom")):
            with self.assertRaises(state.HwahapError) as raised:
                state.transition(args)
        self.assertEqual(raised.exception.code, "HW_REPORT_GENERATION_FAILED")
        self.assertEqual((run_path.read_bytes(), events_path.read_bytes()), before)
        self.assertFalse((run_dir / "report-data.json").exists())
        self.assertFalse((run_dir / "report.html").exists())

    def test_cancelled_is_allowed_from_every_nonterminal_predecessor(self):
        predecessors = (
            "initialized", "contract_locked", "implementing", "reviewing",
            "recovering", "replanning", "final_review")
        for predecessor in predecessors:
            with self.subTest(predecessor=predecessor):
                self.assertIn("cancelled", state.RUN_TRANSITIONS[predecessor])
