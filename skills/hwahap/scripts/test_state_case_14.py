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
        def test_completed_report_rejects_canonical_html_tamper_with_coordinated_hash(self) -> None:
            run_dir = self.prepare_final_review()
            with redirect_stdout(io.StringIO()):
                hwahap_state.complete_run(self.complete_args())
            report_path, data_path, run_path = (run_dir / "report.html", run_dir / "report-data.json", run_dir / "run.json")
            original_html, original_data, original_run = report_path.read_bytes(), data_path.read_bytes(), run_path.read_bytes()
            for replacement in (b"</main>", b"aggregate status: pass"):
                with self.subTest(replacement=replacement):
                    if replacement == b"</main>":
                        tampered_html = original_html.replace(replacement, b'<p>extra-canonical-markup</p></main>', 1)
                    else:
                        tampered_html = original_html.replace(replacement, b"aggregate status: fail", 1)
                    self.assertNotEqual(tampered_html, original_html)
                    report_path.write_bytes(tampered_html)
                    run = json.loads(original_run)
                    run["report"]["html"]["file_sha256"] = "sha256:" + hashlib.sha256(tampered_html).hexdigest()
                    self.write_json(run_path, run)
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        self.validate()
                    self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                    self.assertIn("report HTML does not match canonical renderer", str(raised.exception))
                    self.assertEqual(data_path.read_bytes(), original_data)
                    report_path.write_bytes(original_html)
                    run_path.write_bytes(original_run)

        def test_hardlinked_state_files_are_rejected_without_canary_change(self) -> None:
            for name in ("contract.json", "unit-1.json", "events.jsonl", "run.json"):
                with self.subTest(name=name):
                    run_dir = self.prepare_final_review()
                    path = run_dir / "units" / name if name == "unit-1.json" else run_dir / name
                    before = path.read_bytes()
                    victim = self.workspace / ("hardlink-" + name)
                    victim.write_bytes(before)
                    path.unlink()
                    os.link(victim, path)
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        if name == "run.json":
                            hwahap_state.complete_run(self.complete_args())
                        else:
                            self.validate()
                    self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                    self.assertEqual(victim.read_bytes(), before)
                    path.unlink()
                    path.write_bytes(before)

            run_dir = self.prepare_final_review()
            with redirect_stdout(io.StringIO()):
                hwahap_state.complete_run(self.complete_args())
            run_path = run_dir / "run.json"
            before = run_path.read_bytes()
            victim = self.workspace / "hardlink-goal-run.json"
            victim.write_bytes(before)
            run_path.unlink()
            os.link(victim, run_path)
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.goal_complete_sync(self.goal_complete_args())
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertEqual(victim.read_bytes(), before)
