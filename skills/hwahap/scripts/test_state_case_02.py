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
        def test_fast_status_stays_unknown_without_platform_receipt(self) -> None:
            run_dir = self.prepare_final_review()
            run_path = run_dir / "run.json"
            baseline_run = run_path.read_bytes()
            for forged in ("enabled", "disabled"):
                with self.subTest(fast_status=forged):
                    run = json.loads(baseline_run)
                    run["fast_status"] = forged
                    self.write_json(run_path, run)
                    original = {name: (run_dir / name).read_bytes() for name in ("run.json", "events.jsonl")}
                    for operation in (self.validate, lambda: hwahap_state.complete_run(self.complete_args())):
                        with self.assertRaises(hwahap_state.HwahapError) as raised:
                            operation()
                        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                    for name, data in original.items():
                        self.assertEqual((run_dir / name).read_bytes(), data)
                    self.assertFalse((run_dir / "report-data.json").exists())
                    self.assertFalse((run_dir / "report.html").exists())
                    run_path.write_bytes(baseline_run)
            self.assertEqual(json.loads((run_dir / "run.json").read_text())["fast_status"], "unknown")
            with redirect_stdout(io.StringIO()):
                hwahap_state.complete_run(self.complete_args())
            self.assertEqual(json.loads((run_dir / "report-data.json").read_text())["provenance"]["fast_status"], "unknown")
            self.assertIn("unknown", (run_dir / "report.html").read_text())

        def test_v3_report_receipt_is_rejected_without_migration(self) -> None:
            run_dir = self.init_run()
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            run["report"] = {"schema_version": 3, "status": "pending",
                              "generator": {"name": "hwahap-report", "version": 3,
                                            "design_system": "material-design-3"},
                              "source_payload_sha256": None,
                              "data": {"path": "report-data.json", "file_sha256": None},
                              "html": {"path": "report.html", "file_sha256": None},
                              "generated_at": None, "redaction_policy": "hwahap-report-v3"}
            self.write_json(run_path, run)
            self.assert_invalid("report receipt")

        def test_report_v4_data_and_receipt_tampering_are_rejected(self) -> None:
            run_dir = self.prepare_final_review()
            with redirect_stdout(io.StringIO()):
                hwahap_state.complete_run(self.complete_args())
            data_path, run_path = run_dir / "report-data.json", run_dir / "run.json"
            original = data_path.read_bytes()
            data_path.write_bytes(original + b"\n")
            self.assert_invalid("report data digest")
            data_path.write_bytes(original)
            run = json.loads(run_path.read_text())
            run["report"]["data"]["file_sha256"] = "sha256:" + "a" * 64
            self.write_json(run_path, run)
            self.assert_invalid("report data digest")

        def test_report_v4_pending_artifact_and_goal_sync_require_data(self) -> None:
            run_dir = self.init_run()
            (run_dir / "report-data.json").write_bytes(b"{}")
            self.assert_invalid("pending report must not have report artifacts")
            (run_dir / "report-data.json").unlink()
            run_dir = self.prepare_final_review()
            with redirect_stdout(io.StringIO()):
                hwahap_state.complete_run(self.complete_args())
            (run_dir / "report-data.json").unlink()
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.goal_complete_sync(self.goal_complete_args())
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
