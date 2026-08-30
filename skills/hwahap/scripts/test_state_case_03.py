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
        def test_report_artifact_write_and_final_validate_failures_roll_back(self) -> None:
            for target in ("report-data.json", "report.html", "run.json", "events.jsonl", "validate"):
                with self.subTest(command="complete", target=target):
                    run_dir = self.prepare_final_review()
                    run_path, events_path = run_dir / "run.json", run_dir / "events.jsonl"
                    before = (run_path.read_bytes(), events_path.read_bytes())
                    original_atomic = hwahap_state._atomic_replace_bytes
                    def fail_bytes(path: Path, data: bytes) -> None:
                        if path.name == target:
                            raise OSError("report-artifact-canary")
                        return original_atomic(path, data)
                    original_validate = hwahap_state.validate_run
                    calls = 0
                    def fail_validate(args: Namespace) -> None:
                        nonlocal calls
                        calls += 1
                        if calls > 1:
                            raise hwahap_state.HwahapError("HW_STATE_INVALID", "report-artifact-canary")
                        original_validate(args)
                    try:
                        with patch.object(hwahap_state, "_atomic_replace_bytes", new=fail_bytes), patch.object(hwahap_state, "validate_run", new=fail_validate if target == "validate" else original_validate):
                            with self.assertRaises(hwahap_state.HwahapError) as raised:
                                hwahap_state.complete_run(self.complete_args())
                    finally:
                        hwahap_state.validate_run = original_validate
                    if (run_dir / ".report-recovery.json").exists():
                        self.validate()
                    self.assertEqual(raised.exception.code, "HW_REPORT_GENERATION_FAILED")
                    self.assertEqual(before, (run_path.read_bytes(), events_path.read_bytes()))
                    self.assertFalse((run_dir / "report-data.json").exists())
                    self.assertFalse((run_dir / "report.html").exists())

            run_dir = self.prepare_final_review()
            with redirect_stdout(io.StringIO()):
                hwahap_state.complete_run(self.complete_args())
            for target in ("report-data.json", "report.html", "run.json", "validate"):
                with self.subTest(command="goal_sync", target=target):
                    run_path, data_path, report_path = run_dir / "run.json", run_dir / "report-data.json", run_dir / "report.html"
                    before = (run_path.read_bytes(), data_path.read_bytes(), report_path.read_bytes())
                    original_atomic, original_validate = hwahap_state._atomic_replace_bytes, hwahap_state.validate_run
                    def fail_bytes(path: Path, data: bytes) -> None:
                        if path.name == target:
                            raise OSError("goal-artifact-canary")
                        return original_atomic(path, data)
                    calls = 0
                    def fail_validate(args: Namespace) -> None:
                        nonlocal calls
                        calls += 1
                        if calls > 1:
                            raise hwahap_state.HwahapError("HW_STATE_INVALID", "goal-artifact-canary")
                        original_validate(args)
                    try:
                        with patch.object(hwahap_state, "_atomic_replace_bytes", new=fail_bytes), patch.object(hwahap_state, "validate_run", new=fail_validate if target == "validate" else original_validate):
                            with self.assertRaises(hwahap_state.HwahapError) as raised:
                                hwahap_state.goal_complete_sync(self.goal_complete_args())
                    finally:
                        hwahap_state.validate_run = original_validate
                    if (run_dir / ".report-recovery.json").exists():
                        self.validate()
                    self.assertEqual(raised.exception.code, "HW_REPORT_GENERATION_FAILED")
                    self.assertEqual(before, (run_path.read_bytes(), data_path.read_bytes(), report_path.read_bytes()))
