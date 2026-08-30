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
        def test_events_reject_illegal_terminal_and_current_mismatch(self) -> None:
            run_dir = self.init_run()
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            for name, status, transitions, expected in (
                ("illegal", "contract_locked", [("run", "initialized", "completed")], "illegal transition"),
                ("terminal", "blocked", [("run", "initialized", "blocked"), ("run", "blocked", "implementing")], "terminal state"),
                ("mismatch", "implementing", [("run", "initialized", "contract_locked"), ("run", "initialized", "implementing")], "current state mismatch"),
            ):
                with self.subTest(case=name):
                    current = copy.deepcopy(run)
                    current["status"] = status
                    if status == "blocked":
                        current["failure"] = {"code": "HW_IMPLEMENTATION_BLOCKED", "reason": "test", "evidence": ["test"], "recovery": "retry"}
                    self.write_json(run_path, current)
                    self.write_events(run_dir, transitions)
                    self.assert_invalid(expected)

        def test_review_rejects_wrong_reviewer_digest_and_scope(self) -> None:
            run_dir = self.init_run()
            self.lock_contract(run_dir)
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            run["status"] = "reviewing"
            self.write_json(run_path, run)
            unit = self.passed_unit()
            unit_path = run_dir / "units" / "unit-1.json"
            self.write_json(unit_path, unit)
            self.write_events(run_dir, self.phase_events("passed"))
            self.validate()
            for field, value, expected in (
                ("model", "gpt-5.6-sol", "model or effort"),
                ("diff_digest", "sha256:" + "b" * 64, "diff digest"),
                ("changed_paths", ["outside/file"], "outside unit scope"),
            ):
                with self.subTest(field=field):
                    current = copy.deepcopy(unit)
                    if field == "changed_paths":
                        current["review_history"][0][field] = value
                    else:
                        current["review_history"][0]["verifier"][field] = value
                    self.write_json(unit_path, current)
                    self.assert_invalid("diff fields" if field == "changed_paths" else expected)
