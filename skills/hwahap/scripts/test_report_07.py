try:
    from .test_reportkit import *
except ImportError:
    from test_reportkit import *

class ReportSlice14Tests(HwahapReportTests):
    def test_other_header_variants_are_redacted_across_payload_and_html(self) -> None:
            contract, run, units, events, digests = self.fixture()
            variants = (
                "X-Api-Key: [redacted]\rresponse=report-api-fold-secret",
                "X-Api-Key: report-api-prefix-secret [redacted]",
                "Cookie: [redacted]\r\n\treport-cookie-fold-secret",
                "Cookie: report-cookie-prefix-secret [redacted]",
                "Password: [redacted]\rreport-password-fold-secret",
                "Password: report-password-prefix-secret [redacted]",
                "x_api_key=Basic report-x-under-basic-secret",
                "x-api-key=Digest report-x-hyphen-digest-secret",
                "x api key: Bearer report-x-spaced-bearer-secret",
                "x_api_key=Basic [redacted]\nSECRET_KEY=report-overlap-secret",
                "Authorization: Basic <report-auth-angle-prefix>",
                "Proxy-Authorization: Digest report-proxy-angle-prefix<report-proxy-angle-suffix>",
                "X-Api-Key: <report-x-angle-prefix>",
                "x_api_key=Basic report-x-under-angle-prefix<report-x-under-angle-suffix>",
                "Cookie: <report-cookie-angle-prefix>",
                "Password: report-password-angle-prefix<report-password-angle-suffix>",
                "Private-Key: <report-private-angle-prefix>",
            )
            safe_variants = ("x_api_key=Basic [redacted]", "X_API_KEY=Digest [redacted]", "x api key: Bearer [redacted]")
            run["deferred_security"] = [{"summary": "deferred", "reason": variants[0], "next_action": "wait", "evidence": list(variants[1:]) + list(safe_variants)}]
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            encoded = json.dumps(payload, ensure_ascii=False)
            digest = report.canonical_payload_digest(payload)
            text = report.render_report(payload, digest).decode()
            for value in ("report-api-fold-secret", "report-api-prefix-secret", "report-cookie-fold-secret",
                "report-cookie-prefix-secret", "report-password-fold-secret", "report-password-prefix-secret",
                "report-x-under-basic-secret", "report-x-hyphen-digest-secret", "report-x-spaced-bearer-secret",
                "report-auth-angle-prefix", "report-proxy-angle-prefix", "report-proxy-angle-suffix",
                "report-x-angle-prefix", "report-x-under-angle-prefix", "report-x-under-angle-suffix",
                "report-cookie-angle-prefix", "report-password-angle-prefix", "report-password-angle-suffix",
                "report-private-angle-prefix"):
                self.assertNotIn(value, encoded)
                self.assertNotIn(value, text)
            self.assertNotIn("report-overlap-secret", encoded)
            self.assertNotIn("report-overlap-secret", text)
            for value in variants:
                cleaned = report._text(value)
                self.assertEqual(report._text(cleaned), cleaned)
                self.assertNotIn("[redacted] [redacted]", cleaned)
                self.assertNotIn("[redacted] [redacted]", encoded)
                self.assertNotIn("[redacted] [redacted]", text)
            for marker in ("X-Api-Key: [redacted]", "Cookie: [redacted]", "Password: [redacted]",
                           "Authorization: Basic [redacted]", "Proxy-Authorization: Digest [redacted]",
                           "Private-Key: [redacted]"):
                self.assertIn(marker, encoded)
                self.assertIn(marker, text)
            for safe in ("X-Api-Key: [redacted]", "Cookie: [redacted]", "Password: [redacted]"):
                self.assertFalse(report.credential_bearing_text(safe))
                self.assertEqual(report._text(safe), safe)
            for safe in safe_variants:
                self.assertFalse(report.credential_bearing_text(safe))
                self.assertEqual(report._text(report._text(safe)), report._text(safe))
            self.assertTrue(report.validate_report_bytes(text.encode(), digest, payload))

class ReportSlice15Tests(HwahapReportTests):
    def test_empty_sections_are_readable(self) -> None:
            contract, run, _, events, digests = self.fixture()
            payload = report.build_payload('/tmp/work', contract, run, [], events, digests)
            text = report.render_report(payload, report.canonical_payload_digest(payload)).decode()
            self.assertGreaterEqual(text.count('기록 없음'), 4)
            self.assertIn('id="units"', text)
            self.assertIn('id="reviews"', text)
            self.assertIn('id="failures-recovery"', text)
            self.assertIn('id="deviations"', text)
