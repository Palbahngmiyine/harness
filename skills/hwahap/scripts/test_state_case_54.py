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
        def test_supported_paths_reject_every_shared_engine_obfuscator(self) -> None:
            marker = "supported-path-canary"
            codepoints = (0x00AD, 0x034F, 0x061C, 0x115F, 0x1160, 0x17B4, 0x17B5,
                          0x180B, 0x200B, 0x2028, 0x2029, 0x2060, 0x3164, 0xFE00,
                          0xFE0F, 0xFFA0, 0xE0100, 0x001F, 0xE000, 0xFDD0, 0xFFFE, 0x1FFFE)
            report_dir = self.init_run("report-probe")
            contract = json.loads((report_dir / "contract.json").read_text())
            clean_run = json.loads((report_dir / "run.json").read_text())
            events = hwahap_state.parse_events(report_dir / "events.jsonl")
            digests = hwahap_state.report_state_digests(report_dir / "contract.json", report_dir / "events.jsonl", report_dir / "units")
            launcher = MODULE_PATH.with_name("hwahap")
            for codepoint in codepoints:
                separator = chr(codepoint)
                raw = f"client{separator}secret: {marker}"
                title = raw
                with self.subTest(codepoint=hex(codepoint)):
                    with tempfile.TemporaryDirectory(dir=self.workspace) as directory:
                        workspace = Path(directory)
                        spec = workspace / "spec.md"
                        spec.write_text(f"---\ntitle: {title}\nstatus: prfaq\nconfirmed_at: 2026-08-27T00:00:00Z\n---\n", encoding="utf-8")
                        self.install_agents(workspace)
                        result = subprocess.run(
                            [str(launcher), "init", "--workspace", str(workspace), "--goal-id", "probe", "--spec", str(spec)],
                            cwd=workspace, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                        )
                        self.assertEqual(result.returncode, 1)
                        self.assertEqual(result.stderr, "HW_STATE_INVALID: state is invalid\n")
                        self.assertEqual(result.stdout, "")
                        self.assertFalse((workspace / ".hwahap").exists())
                        self.assertNotIn(marker, result.stdout + result.stderr)
                        self.assertNotIn(str(workspace), result.stdout + result.stderr)
                        self.assertNotIn(separator, result.stdout + result.stderr)

                    errors: list[str] = []
                    hwahap_state.validate_state_strings({"nested": raw}, "probe", errors)
                    self.assertTrue(errors)
                    self.assertNotIn(marker, " ".join(errors))
                    self.assertNotIn(separator, " ".join(errors))
                    probe_run = copy.deepcopy(clean_run)
                    probe_run["deviations"] = [{"summary": "supported path", "root_cause": "probe", "impact": "none",
                                                 "prevention": "test", "evidence": [raw]}]
                    payload = hwahap_report.build_payload(self.workspace, contract, probe_run, [], events, digests)
                    encoded = hwahap_report.canonical_payload_bytes(payload)
                    digest = hwahap_report.canonical_payload_digest(payload)
                    self.assertNotIn(marker.encode(), encoded)
                    self.assertTrue(hwahap_report.validate_report_data_bytes(encoded, payload, digest))
                    html = hwahap_report.render_report(payload, digest)
                    self.assertNotIn(marker.encode(), html)
                    self.assertTrue(hwahap_report.validate_report_bytes(html, digest, payload))

            for value in ("Authorization: Bearer [redacted]", "Proxy-Authorization: Digest [redacted]", "token_total=3"):
                self.assertFalse(hwahap_state.credential_bearing_text(value))
                self.assertFalse(hwahap_report.credential_bearing_text(value))

        def test_nested_string_keys_are_checked_without_echoing_them(self) -> None:
            keys = ("client-secret=whole-feature-key-canary", "Authorization: Bearer key-canary",
                    "Proxy-Authorization: Digest proxy-canary", "client\u2028secret=unicode-canary")
            for key in keys:
                with self.subTest(key=key):
                    errors: list[str] = []
                    hwahap_state.validate_state_strings({"nested": {key: "safe"}}, "probe", errors)
                    self.assertTrue(errors)
                    self.assertNotIn(key, " ".join(errors))
            run_dir = self.prepare_final_review()
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            run["deviations"] = [{"client-secret=whole-feature-key-canary": "safe",
                                   "summary": "bounded deviation", "root_cause": "cause",
                                   "impact": "none", "prevention": "test", "evidence": ["evidence"]}]
            run["metrics"]["scope_deviations"] = 1
            self.write_json(run_path, run)
            original = {name: (run_dir / name).read_bytes() for name in ("run.json", "events.jsonl")}
            for operation in (self.validate, lambda: hwahap_state.complete_run(self.complete_args())):
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    operation()
                self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                self.assertNotIn("whole-feature-key-canary", str(raised.exception))
            self.assertEqual((run_dir / "run.json").read_bytes(), original["run.json"])
            self.assertEqual((run_dir / "events.jsonl").read_bytes(), original["events.jsonl"])
            self.assertFalse((run_dir / "report-data.json").exists())
            self.assertFalse((run_dir / "report.html").exists())
