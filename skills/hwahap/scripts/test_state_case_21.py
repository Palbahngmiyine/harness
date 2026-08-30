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
        def test_goal_sync_rejects_rebind_and_rolls_back(self) -> None:
            run_dir = self.init_run()
            first = self.goal_args(
                "bound", thread_id="goal-thread", objective_sha256="sha256:" + "a" * 64,
                receipt_sha256="sha256:" + "b" * 64,
            )
            with redirect_stdout(io.StringIO()):
                hwahap_state.goal_sync(first)
            before = (run_dir / "run.json").read_bytes()
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.goal_sync(self.goal_args(
                    "bound", thread_id="other-thread", objective_sha256="sha256:" + "c" * 64,
                    receipt_sha256="sha256:" + "d" * 64,
                ))
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertEqual((run_dir / "run.json").read_bytes(), before)

            original_validate = hwahap_state.validate_run
            calls = 0
            def fail_after_write(args: Namespace) -> None:
                nonlocal calls
                calls += 1
                if calls > 1:
                    raise hwahap_state.HwahapError("HW_STATE_INVALID", "forced validation failure")
                original_validate(args)
            hwahap_state.validate_run = fail_after_write
            try:
                with self.assertRaises(hwahap_state.HwahapError):
                    hwahap_state.goal_sync(self.goal_args(
                        "no_active_goal", receipt_sha256="sha256:" + "e" * 64,
                    ))
            finally:
                hwahap_state.validate_run = original_validate
            self.assertEqual((run_dir / "run.json").read_bytes(), before)

        def test_goal_sync_write_then_raise_restores_state(self) -> None:
            run_dir = self.init_run()
            run_path = run_dir / "run.json"
            before = run_path.read_bytes()
            original_write_text = Path.write_text

            def write_then_raise(path: Path, *args: object, **kwargs: object) -> int:
                result = original_write_text(path, *args, **kwargs)
                if path == run_path:
                    raise OSError("secret Goal write")
                return result

            with patch.object(Path, "write_text", new=write_then_raise):
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.goal_sync(self.goal_args(
                        "no_active_goal", receipt_sha256="sha256:" + "a" * 64))
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertNotIn("secret Goal write", str(raised.exception))
            self.assertEqual(run_path.read_bytes(), before)
