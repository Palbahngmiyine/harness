try:
    from .test_terminalkit import *
    from .test_handoffkit import write_goal_artifact
except ImportError:
    from test_terminalkit import *
    from test_handoffkit import write_goal_artifact


class AlignedTerminalFidelityTests(TerminalReportFixture, unittest.TestCase):
    def transition_aligned(self, outcome):
        goal_id = "aligned-" + outcome.replace("_", "-")
        source = write_goal_artifact(self.fixture.workspace)
        with redirect_stdout(io.StringIO()):
            state.init_run(state_tests.Namespace(workspace=str(self.fixture.workspace),
                goal_id=goal_id, goal_spec=str(source)))
        values = {"run_id": goal_id}
        if outcome != "cancelled":
            values.update({"failure_code": "HW_IMPLEMENTATION_FAILED",
                "failure_reason": "terminal test failure",
                "failure_evidence": ["terminal evidence"],
                "failure_recovery": "review the terminal evidence"})
        with redirect_stdout(io.StringIO()):
            state.transition(self.fixture.transition_args("run", outcome, **values))
        return self.fixture.workspace / ".hwahap" / "runs" / goal_id

    def test_every_non_success_terminal_report_preserves_source_handoff(self):
        for outcome in ("blocked", "failed", "awaiting_user", "cancelled"):
            with self.subTest(outcome=outcome):
                run_dir = self.transition_aligned(outcome)
                payload = json.loads((run_dir / "report-data.json").read_text())
                handoff = payload["contract"]["spec"]["handoff"]
                self.assertEqual(handoff["schema"], "align-goal/v1")
                self.assertEqual(handoff["implementation_units"][0]["id"], "U1")
                self.assertEqual(payload["summary"]["status"], outcome)
                self.assertIn("align-goal source", (run_dir / "report.html").read_text())


if __name__ == "__main__":
    unittest.main()
