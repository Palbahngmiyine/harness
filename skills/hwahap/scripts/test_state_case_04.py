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
        def test_report_recovery_journal_retries_incomplete_restore_on_next_validate(self) -> None:
            run_dir = self.prepare_final_review()
            data_path, report_path = run_dir / "report-data.json", run_dir / "report.html"
            original_write, original_unlink = hwahap_state._atomic_replace_bytes, Path.unlink
            writes = {"restore_failed": False}

            def fault(path: Path, data: bytes, **kwargs: object) -> int:
                if path == report_path:
                    raise OSError("journal-report-canary")
                return original_write(path, data)

            def fault_unlink(path: Path, **kwargs: object) -> None:
                if path == data_path and not writes["restore_failed"]:
                    writes["restore_failed"] = True
                    raise OSError("journal-restore-canary")
                return original_unlink(path, **kwargs)

            try:
                with patch.object(hwahap_state, "_atomic_replace_bytes", new=fault), patch.object(Path, "unlink", new=fault_unlink):
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        hwahap_state.complete_run(self.complete_args())
            finally:
                hwahap_state._atomic_replace_bytes, Path.unlink = original_write, original_unlink
            self.assertEqual(raised.exception.code, "HW_REPORT_GENERATION_FAILED")
            journal = run_dir / ".report-recovery.json"
            self.assertTrue(journal.is_file())
            self.assertTrue(data_path.is_file())
            self.assertFalse(report_path.exists())
            self.validate()
            self.assertFalse(journal.exists())
            self.assertFalse(data_path.exists())
            self.assertFalse(report_path.exists())

        def test_malformed_report_recovery_journal_is_rejected(self) -> None:
            run_dir = self.init_run()
            (run_dir / ".report-recovery.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                self.validate()
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")

        def test_unbound_recovery_journal_only_clears_exact_original_set(self) -> None:
            run_dir = self.prepare_final_review()
            files = {name: (run_dir / name).read_bytes() for name in ("run.json", "events.jsonl")}
            originals = {"run.json": (True, files["run.json"]), "report-data.json": (False, b""),
                         "report.html": (False, b""), "events.jsonl": (True, files["events.jsonl"])}
            target = {name: (run_dir / name).read_bytes() if (run_dir / name).exists() else b"target"
                      for name in hwahap_state._REPORT_RECOVERY_FILES}
            journal, _ = hwahap_state._recovery_setup("complete", originals, target)
            journal_path = run_dir / ".report-recovery.json"
            journal_path.write_bytes(journal)
            self.validate()
            self.assertFalse(journal_path.exists())
            journal_path.write_bytes(journal)
            (run_dir / "report-data.json").write_bytes(b"unexpected")
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                self.validate()
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertEqual((run_dir / "report-data.json").read_bytes(), b"unexpected")

        def test_unbound_recovery_cleanup_failure_and_orphan_marker_are_invalid(self) -> None:
            run_dir = self.prepare_final_review()
            files = {name: (run_dir / name).read_bytes() for name in ("run.json", "events.jsonl")}
            originals = {"run.json": (True, files["run.json"]), "report-data.json": (False, b""),
                         "report.html": (False, b""), "events.jsonl": (True, files["events.jsonl"])}
            target = {name: (run_dir / name).read_bytes() if (run_dir / name).exists() else b"target"
                      for name in hwahap_state._REPORT_RECOVERY_FILES}
            journal, _ = hwahap_state._recovery_setup("complete", originals, target)
            journal_path = run_dir / ".report-recovery.json"
            journal_path.write_bytes(journal)
            with patch.object(hwahap_state, "_clear_report_recovery_journal", return_value=False):
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    self.validate()
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertTrue(journal_path.exists())
            journal_path.unlink()
            run = json.loads((run_dir / "run.json").read_text())
            run["report_transaction"] = {"transaction_id": "sha256:" + "a" * 64}
            self.write_json(run_dir / "run.json", run)
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                self.validate()
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
