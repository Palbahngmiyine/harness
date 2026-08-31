"""Focused compatibility checks for credential and direct report imports."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))


def load_report():
    spec = importlib.util.spec_from_file_location("compat_report", ROOT / "hwahap_report.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class CredentialReportCompatibilityTests(unittest.TestCase):
    def test_legacy_credential_and_redaction_exports(self):
        import hwahap_credentials as credentials
        import hwahap_redaction as redaction

        value = "Authorization: Bearer compat-secret"
        self.assertTrue(credentials.contains_sensitive_data(value))
        self.assertEqual(credentials.redact(value), "Authorization: Bearer [redacted]")
        self.assertIs(redaction.SensitiveDataFinding, credentials.CredentialFinding)
        self.assertEqual(redaction.redact(value), "Authorization: Bearer [redacted]")

    def test_direct_report_import_exposes_legacy_surface(self):
        report = load_report()
        for name in ("EVENT_FIELDS", "CONTRACT_LISTS", "REPORT_IDS", "SHA256",
                     "build_payload", "canonical_payload_bytes", "render_report"):
            self.assertTrue(hasattr(report, name), name)
        self.assertTrue(report.credential_bearing_text("client_secret=compat"))
        self.assertEqual(report._text("client_secret=compat"), "client_secret=[redacted]")


if __name__ == "__main__":
    unittest.main()
