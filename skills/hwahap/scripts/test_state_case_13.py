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
        def test_complete_event_write_failure_restores_run_and_removes_report(self) -> None:
            run_dir = self.prepare_final_review()
            run_path, events_path = run_dir / "run.json", run_dir / "events.jsonl"
            report_path = run_dir / "report.html"
            run_before, events_before = run_path.read_bytes(), events_path.read_bytes()
            original_atomic = hwahap_state._atomic_replace_bytes

            def fail_events(path: Path, data: bytes) -> None:
                if path == events_path:
                    raise OSError("secret event write")
                return original_atomic(path, data)

            with patch.object(hwahap_state, "_atomic_replace_bytes", new=fail_events):
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.complete_run(self.complete_args())
            self.assertEqual(raised.exception.code, "HW_REPORT_GENERATION_FAILED")
            self.assertNotIn("secret event write", str(raised.exception))
            self.validate()
            self.assertEqual(run_path.read_bytes(), run_before)
            self.assertEqual(events_path.read_bytes(), events_before)
            self.assertFalse(report_path.exists())

        def test_complete_existing_or_symlink_report_does_not_write(self) -> None:
            for symlink in (False, True):
                with self.subTest(symlink=symlink):
                    run_dir = self.prepare_final_review()
                    report_path = run_dir / "report.html"
                    if symlink:
                        target = self.workspace / "outside.html"
                        target.write_text("outside", encoding="utf-8")
                        report_path.symlink_to(target)
                    else:
                        report_path.write_text("existing", encoding="utf-8")
                    before = (run_dir / "run.json").read_bytes()
                    with self.assertRaises(hwahap_state.HwahapError):
                        hwahap_state.complete_run(self.complete_args())
                    self.assertEqual((run_dir / "run.json").read_bytes(), before)
                    report_path.unlink()

        def test_completed_report_tamper_and_missing_receipt_are_rejected(self) -> None:
            run_dir = self.prepare_final_review()
            with redirect_stdout(io.StringIO()):
                hwahap_state.complete_run(self.complete_args())
            events_path = run_dir / "events.jsonl"
            original_events = events_path.read_bytes()
            events = hwahap_state.parse_events(events_path)
            events[-1]["reason"] = "tampered source"
            events_path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
            self.assert_invalid("report source digest does not match state")
            events_path.write_bytes(original_events)
            report_path = run_dir / "report.html"
            report_path.write_bytes(report_path.read_bytes() + b"tamper")
            self.assert_invalid("report file digest")
            run = json.loads((run_dir / "run.json").read_text())
            run.pop("report")
            self.write_json(run_dir / "run.json", run)
            self.assert_invalid("report receipt")
