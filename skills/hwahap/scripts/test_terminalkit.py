"""Shared fixture and imports for terminal report tests."""

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest import mock

try:
    from . import test_state_case_01 as state_tests
except ImportError:
    import test_state_case_01 as state_tests

state = state_tests.hwahap_state


def load_tests(loader, tests, pattern):
    if pattern is None:
        return tests
    return unittest.TestSuite()


class TerminalReportFixture:
    def setUp(self):
        self.fixture = state_tests.HwahapStateTests(methodName="runTest")
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def transition_to(self, goal_id, outcome):
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


__all__ = [name for name in globals() if not name.startswith("__")]
