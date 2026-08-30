"""Terminal outcome report regressions."""

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest import mock

from skills.hwahap.scripts import test_hwahap_state as state_tests

state = state_tests.hwahap_state


class TerminalReportTests(unittest.TestCase):
    def setUp(self):
        self.fixture = state_tests.HwahapStateTests(methodName="runTest")
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def _transition(self, goal_id, outcome):
        self.fixture.init_run(goal_id)
        values = {"run_id": goal_id}
        if outcome != "cancelled":
            values.update({
                "failure_code": "HW_IMPLEMENTATION_FAILED",
                "failure_reason": "terminal test failure",
                "failure_evidence": ["terminal evidence"],
                "failure_recovery": "review the terminal evidence",
            })
        args = self.fixture.transition_args("run", outcome, **values)
        with redirect_stdout(io.StringIO()):
            state.transition(args)
        return self.fixture.workspace / ".hwahap" / "runs" / goal_id

    def test_every_non_success_terminal_outcome_generates_valid_report(self):
        for outcome in ("blocked", "failed", "awaiting_user", "cancelled"):
            with self.subTest(outcome=outcome):
                run_dir = self._transition("terminal-" + outcome.replace("_", "-"), outcome)
                self.fixture.validate("terminal-" + outcome.replace("_", "-"))
                run = json.loads((run_dir / "run.json").read_text())
                payload = json.loads((run_dir / "report-data.json").read_text())
                self.assertEqual(run["report"]["status"], "completed")
                self.assertEqual(payload["summary"]["status"], outcome)
                self.assertTrue((run_dir / "report.html").is_file())
                if outcome != "cancelled":
                    self.assertEqual(payload["failures-recovery"][0]["unit_id"], "run")

    def test_terminal_report_failure_rolls_back_all_files(self):
        run_dir = self.fixture.init_run("terminal-rollback")
        run_path, events_path = run_dir / "run.json", run_dir / "events.jsonl"
        before = run_path.read_bytes(), events_path.read_bytes()
        args = self.fixture.transition_args("run", "cancelled", run_id="terminal-rollback")
        with mock.patch.object(state, "prepare_report_artifacts", side_effect=ValueError("boom")):
            with self.assertRaises(state.HwahapError) as raised:
                state.transition(args)
        self.assertEqual(raised.exception.code, "HW_REPORT_GENERATION_FAILED")
        self.assertEqual((run_path.read_bytes(), events_path.read_bytes()), before)
        self.assertFalse((run_dir / "report-data.json").exists())
        self.assertFalse((run_dir / "report.html").exists())


if __name__ == "__main__":
    unittest.main()
