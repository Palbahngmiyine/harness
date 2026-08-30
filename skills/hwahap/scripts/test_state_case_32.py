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
        def test_record_test_receipt_computes_pass_fail_timeout_fields(self) -> None:
            run_dir = self.prepare_reviewing_test_unit()
            for outcome, overrides in (("pass", {"exit_code": 0}), ("fail", {"execution_receipt_sha256": "sha256:" + "1" * 64, "exit_code": 7}),
                                       ("timeout", {"execution_receipt_sha256": "sha256:" + "2" * 64, "exit_code": None, "timed_out": True})):
                with self.subTest(outcome=outcome), redirect_stdout(io.StringIO()) as output:
                    hwahap_state.record_test_receipt(self.record_receipt_args(**overrides))
                    self.assertIn(f"status={outcome}", output.getvalue())
            receipt = json.loads((run_dir / "units" / "unit-1.json").read_text())["test_receipts"]
            self.assertEqual([item["test_id"] for item in receipt], ["test-1-1", "test-1-2", "test-1-3"])
            self.assertEqual([item["status"] for item in receipt], ["pass", "fail", "timeout"])
            self.assertTrue(all(item["source"] == "codex.exec_command" and item["observer_role"] == "verifier" for item in receipt))
            self.validate()

        def test_record_test_receipt_rejects_invalid_duplicate_and_wrong_state(self) -> None:
            run_dir = self.prepare_reviewing_test_unit()
            args = self.record_receipt_args()
            bad = (self.record_receipt_args(exit_code=0, timed_out=True),
                   self.record_receipt_args(execution_receipt_sha256="bad"),
                   self.record_receipt_args(observer_thread_id=""))
            for invalid in bad:
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.record_test_receipt(invalid)
                self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            with redirect_stdout(io.StringIO()):
                hwahap_state.record_test_receipt(args)
            before = (run_dir / "units" / "unit-1.json").read_bytes()
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.record_test_receipt(args)
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertEqual((run_dir / "units" / "unit-1.json").read_bytes(), before)
            run = json.loads((run_dir / "run.json").read_text())
            unit = json.loads((run_dir / "units" / "unit-1.json").read_text())
            run["status"], unit["status"] = "implementing", "implementing"
            self.write_json(run_dir / "run.json", run)
            self.write_json(run_dir / "units" / "unit-1.json", unit)
            self.write_events(run_dir, [
                ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
                ("unit-1", "planned", "implementing"),
            ])
            self.validate()
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.record_test_receipt(self.record_receipt_args())
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")

        def test_record_test_receipt_rolls_back_and_cli_help_is_available(self) -> None:
            run_dir = self.prepare_reviewing_test_unit()
            unit_path = run_dir / "units" / "unit-1.json"
            run_path = run_dir / "run.json"
            before, run_before = unit_path.read_bytes(), run_path.read_bytes()
            original = hwahap_state.validate_run
            calls = 0
            def fail_after_write(args: Namespace) -> None:
                nonlocal calls
                calls += 1
                if calls > 1:
                    raise hwahap_state.HwahapError("HW_STATE_INVALID", "forced receipt validation failure")
                original(args)
            hwahap_state.validate_run = fail_after_write
            try:
                with self.assertRaises(hwahap_state.HwahapError):
                    hwahap_state.record_test_receipt(self.record_receipt_args())
            finally:
                hwahap_state.validate_run = original
            self.assertEqual(unit_path.read_bytes(), before)
            self.assertEqual(run_path.read_bytes(), run_before)
            with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()) as output:
                hwahap_state.parser().parse_args(["record-test-receipt", "--help"])
            self.assertIn("--execution-receipt-sha256", output.getvalue())
            self.assertIn("--timed-out", output.getvalue())
            with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()) as output:
                hwahap_state.parser().parse_args(["run-test", "--help"])
            self.assertIn("execution is disabled", output.getvalue())
