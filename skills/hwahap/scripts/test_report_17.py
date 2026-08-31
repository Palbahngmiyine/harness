try:
    from .test_reportkit import *
except ImportError:
    from test_reportkit import *

class ReportSlice43Tests(HwahapReportTests):
    def test_shared_engine_keeps_dropped_first_view_for_leading_obfuscators(self) -> None:
            state._ensure_dependencies()
            engine = state._dependency_modules[1]
            for raw, expected_kind, expected_text, expected_value in (
                ("\u200bclient-secret=span-canary", "assignment", "client-secret=span-canary", "span-canary"),
                ("\u200bAuthorization: Bearer span-canary", "auth", "Authorization: Bearer span-canary", "Bearer span-canary"),
            ):
                with self.subTest(raw=raw):
                    normalized = engine.normalized_text(raw)
                    matches = engine.findings(raw)
                    finding = next(item for item in matches if item.kind == expected_kind)
                    self.assertEqual(normalized[finding.normalized_start:finding.normalized_end], expected_text)
                    self.assertEqual(normalized[finding.normalized_value_start:finding.normalized_value_end], expected_value)
                    self.assertGreaterEqual(finding.normalized_start, 0)
                    self.assertLessEqual(finding.normalized_end, len(normalized))
                    self.assertGreaterEqual(finding.normalized_value_start, 0)
                    self.assertLessEqual(finding.normalized_value_end, len(normalized))
                    self.assertEqual(raw[finding.start:finding.end], raw[1:])
                    self.assertIn("span-canary", raw[finding.value_start:finding.value_end])
                    cleaned = engine.redact(raw)
                    self.assertNotIn("span-canary", cleaned)
                    self.assertEqual(engine.redact(cleaned), cleaned)

class ReportSlice44Tests(HwahapReportTests):
    def test_redaction_engine_is_loaded_from_sibling_path(self) -> None:
            with tempfile.TemporaryDirectory() as directory:
                Path(directory, "hwahap_credentials.py").write_text(
                    "def credential_bearing_text(value): return False\n", encoding="utf-8")
                previous_cwd = os.getcwd()
                previous = sys.modules.get("hwahap_credentials")
                os.chdir(directory)
                sys.modules["hwahap_credentials"] = object()
                try:
                    for name, path in (("fresh_state", state.__file__), ("fresh_report", report.__file__)):
                        spec = importlib.util.spec_from_file_location(name, path)
                        self.assertIsNotNone(spec)
                        loaded = importlib.util.module_from_spec(spec)
                        assert spec and spec.loader
                        spec.loader.exec_module(loaded)
                        self.assertTrue(loaded.credential_bearing_text("client_secret=sibling-canary"))
                finally:
                    os.chdir(previous_cwd)
                    if previous is None:
                        sys.modules.pop("hwahap_credentials", None)
                    else:
                        sys.modules["hwahap_credentials"] = previous
