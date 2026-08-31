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
        def test_prepare_report_artifacts_is_canonical_and_repeatable(self) -> None:
            run_dir = self.prepare_final_review()
            contract = json.loads((run_dir / "contract.json").read_text())
            run = json.loads((run_dir / "run.json").read_text())
            units = [json.loads(path.read_text()) for path in sorted((run_dir / "units").glob("*.json"))]
            events = hwahap_state.parse_events(run_dir / "events.jsonl")
            digests = hwahap_state.report_state_digests(run_dir / "contract.json", run_dir / "events.jsonl", run_dir / "units")
            first = hwahap_state.prepare_report_artifacts(self.workspace, contract, run, units, events, digests)
            second = hwahap_state.prepare_report_artifacts(self.workspace, contract, run, units, events, digests)
            self.assertEqual(first, second)
            self.assertEqual(first["data_bytes"], hwahap_report.canonical_payload_bytes(first["payload"]))
            self.assertEqual(first["source_payload_sha256"], first["data_file_sha256"])
            self.assertEqual(first["html_file_sha256"], "sha256:" + hashlib.sha256(first["html_bytes"]).hexdigest())
            self.assertNotIn("report-data.json", {path.name for path in run_dir.iterdir()})

        def test_prepare_report_artifacts_normalizes_dependency_failures(self) -> None:
            run_dir = self.prepare_final_review()
            contract = json.loads((run_dir / "contract.json").read_text())
            run = json.loads((run_dir / "run.json").read_text())
            units = [json.loads(path.read_text()) for path in sorted((run_dir / "units").glob("*.json"))]
            events = hwahap_state.parse_events(run_dir / "events.jsonl")
            digests = hwahap_state.report_state_digests(run_dir / "contract.json", run_dir / "events.jsonl", run_dir / "units")
            payload = {"safe": "value"}
            encoded = b'{"safe":"value"}'
            digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
            for broken in ("build_payload", "canonical_payload_bytes", "canonical_payload_digest",
                           "validate_report_data_bytes", "render_report", "validate_report_bytes"):
                with self.subTest(broken=broken):
                    class BrokenReport:
                        def build_payload(self, *args): return (_ for _ in ()).throw(RuntimeError("/private/tmp/credential-canary")) if broken == "build_payload" else payload
                        def canonical_payload_bytes(self, *args): return (_ for _ in ()).throw(RuntimeError("credential-canary")) if broken == "canonical_payload_bytes" else encoded
                        def canonical_payload_digest(self, *args): return (_ for _ in ()).throw(RuntimeError("credential-canary")) if broken == "canonical_payload_digest" else digest
                        def validate_report_data_bytes(self, *args):
                            if broken == "validate_report_data_bytes": raise RuntimeError("credential-canary")
                            return True
                        def render_report(self, *args): return (_ for _ in ()).throw(RuntimeError("credential-canary")) if broken == "render_report" else b"html"
                        def validate_report_bytes(self, *args):
                            if broken == "validate_report_bytes": raise RuntimeError("credential-canary")
                            return True
                    with patch.object(hwahap_state, "report_module", return_value=BrokenReport()):
                        with self.assertRaises(hwahap_state.HwahapError) as raised:
                            hwahap_state.prepare_report_artifacts(self.workspace, contract, run, units, events, digests)
                    self.assertEqual(raised.exception.code, "HW_REPORT_GENERATION_FAILED")
                    self.assertEqual(str(raised.exception), "could not prepare report artifacts")
            with patch.object(hwahap_state, "report_module", return_value=object()):
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.prepare_report_artifacts(self.workspace, contract, run, units, events, digests)
            self.assertEqual(raised.exception.code, "HW_REPORT_GENERATION_FAILED")
            self.assertEqual(str(raised.exception), "could not prepare report artifacts")

        def test_complete_generates_receipt_and_completed_event(self) -> None:
            run_dir = self.prepare_final_review()
            events_path = run_dir / "events.jsonl"
            events_path.write_bytes(events_path.read_bytes().rstrip(b"\n"))
            with redirect_stdout(io.StringIO()):
                hwahap_state.complete_run(self.complete_args())
            run = json.loads((run_dir / "run.json").read_text())
            receipt = run["report"]
            self.assertEqual(run["status"], "completed")
            self.assertEqual(receipt["status"], "completed")
            self.assertTrue(receipt["source_payload_sha256"].startswith("sha256:"))
            self.assertTrue(receipt["data"]["file_sha256"].startswith("sha256:"))
            self.assertTrue(receipt["html"]["file_sha256"].startswith("sha256:"))
            self.assertTrue((run_dir / "report-data.json").read_bytes().startswith(b"{"))
            self.assertTrue((run_dir / "report.html").read_bytes().startswith(b"<!doctype html>"))
            self.assertEqual(run["metrics"]["unit_count"], 1)
            self.assertGreaterEqual(run["metrics"]["elapsed_seconds"], 0)
            self.assertEqual(run["metrics"]["test_runs"], 1)
            self.validate()
            self.assertEqual(hwahap_state.parse_events(run_dir / "events.jsonl")[-1]["to"], "completed")

        def test_report_v4_pending_has_no_physical_artifacts(self) -> None:
            run_dir = self.init_run()
            receipt = json.loads((run_dir / "run.json").read_text())["report"]
            self.assertEqual(receipt, {"schema_version": 3, "status": "pending",
                "generator": {"name": "hwahap-report", "version": 3, "design_system": "material-design-3"},
                "source_payload_sha256": None, "data": {"path": "report-data.json", "file_sha256": None},
                "html": {"path": "report.html", "file_sha256": None}, "generated_at": None,
                "redaction_policy": "hwahap-report-v3"})
            self.assertFalse((run_dir / "report-data.json").exists())
            self.assertFalse((run_dir / "report.html").exists())
