try:
    from .test_terminalkit import *
except ImportError:
    from test_terminalkit import *


class TerminalInvariantTests(TerminalReportFixture, unittest.TestCase):
    def test_pending_report_is_rejected_for_each_terminal_state(self):
        run_dir = self.fixture.init_run("pending-terminal-tamper")
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        for terminal in state.RUN_TERMINAL_STATES:
            with self.subTest(terminal=terminal):
                run["status"] = terminal
                run_path.write_text(json.dumps(run), encoding="utf-8")
                args = state_tests.Namespace(
                    workspace=str(self.fixture.workspace),
                    run_id="pending-terminal-tamper")
                with self.assertRaises(state.HwahapError) as raised:
                    state.validate_run(args)
                self.assertIn(
                    "pending report is invalid for terminal run",
                    str(raised.exception))

    def test_final_review_cancellation_generates_report(self):
        run_dir = self.fixture.prepare_final_review()
        with redirect_stdout(io.StringIO()):
            state.transition(self.fixture.transition_args("run", "cancelled"))
        self.fixture.validate()
        run = json.loads((run_dir / "run.json").read_text())
        self.assertEqual(run["status"], "cancelled")
        self.assertEqual(run["report"]["status"], "completed")

    def test_pending_improvement_cancellation_generates_report(self):
        run_dir = self.fixture.prepare_pending_improvement_run()
        with redirect_stdout(io.StringIO()):
            state.transition(self.fixture.transition_args("run", "cancelled"))
        self.fixture.validate()
        run = json.loads((run_dir / "run.json").read_text())
        self.assertEqual(run["status"], "cancelled")
        self.assertEqual(run["report"]["status"], "completed")
        self.assertTrue((run_dir / "report.html").is_file())
