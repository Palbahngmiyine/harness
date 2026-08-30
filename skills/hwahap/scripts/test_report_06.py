try:
    from .test_reportkit import *
except ImportError:
    from test_reportkit import *

class ReportSlice13Tests(HwahapReportTests):
    def test_authorization_header_variants_are_redacted_across_evidence_sections(self) -> None:
            contract, run, units, events, digests = self.fixture()
            variants = (
                "Authorization: Basic report-basic-secret",
                "Authorization: Digest report-digest-secret",
                'Authorization: Digest username="report-user", realm="report-realm", response="report-response"',
                "Authorization: Basic report-lf-secret\nnext-line",
                "Proxy-Authorization: Basic report-crlf-secret\r\nnext-line",
                'Authorization: Digest username="report-fold-user"\r\n  realm="report-fold-realm"\r\n\tresponse="report-fold-response"',
                "Authorization: Basic [redacted]\r\n\tusername=report-basic-redacted-fold-secret",
                "Authorization: Digest [redacted]\n  username=report-digest-redacted-fold-secret",
                "Proxy-Authorization: Basic [redacted]\r\n\tproxy=report-proxy-redacted-fold-secret",
                "Proxy-Authorization: Bearer report-proxy-bearer-secret",
                "Proxy-Authorization: Basic report-proxy-basic-secret",
                "Proxy-Authorization: Digest report-proxy-digest-secret",
                "X-Api-Key: report-api-key-secret",
                "Authorization: Basic [redacted] report-redacted-tail-secret",
                "Authorization: Digest [redacted] report-digest-redacted-tail-secret",
                "Proxy-Authorization: Digest [redacted] report-proxy-redacted-tail-secret",
                "Authorization: Basic report-prefix-secret [redacted]",
                "Authorization: Digest report-digest-prefix-secret [redacted]",
                "Proxy-Authorization: Digest report-proxy-prefix-secret [redacted]",
                "Authorization: Basic report-basic-cr-secret\rnext-line",
                "Authorization: Digest report-digest-cr-secret\r\tresponse=report-digest-cr-folded",
                "Authorization: Bearer report-bearer-cr-secret\rnext-line",
                "Proxy-Authorization: Basic report-proxy-basic-cr-secret\rnext-line",
                "Proxy-Authorization: Digest report-proxy-digest-cr-secret\r\tresponse=report-proxy-digest-cr-folded",
                "Proxy-Authorization: Bearer report-proxy-bearer-cr-secret\rnext-line",
                "Authorization: Basic [redacted]\rresponse=report-basic-redacted-cr-sentinel",
                "Authorization: Digest [redacted]\rresponse=report-digest-redacted-cr-sentinel",
                "Authorization: Bearer [redacted]\rresponse=report-bearer-redacted-cr-sentinel",
                "Proxy-Authorization: Basic [redacted]\rresponse=report-proxy-basic-redacted-cr-sentinel",
                "Proxy-Authorization: Digest [redacted]\rresponse=report-proxy-digest-redacted-cr-sentinel",
                "Proxy-Authorization: Bearer [redacted]\rresponse=report-proxy-bearer-redacted-cr-sentinel",
            )
            run["deferred_security"] = [{"summary": "deferred", "reason": variants[0], "next_action": "wait", "evidence": [variants[1], variants[2], variants[3], variants[6]]}]
            run["goal_link"]["current"] = {"mode": "unobserved", "reason": variants[4], "evidence": [variants[5], variants[7], variants[9]]}
            units[0]["review_history"] = [{"round": 1, "outcome": "fail", "verifier": {},
                                            "scope_reviewer": {"evidence": [variants[8], variants[10], variants[11], variants[12], variants[13], variants[14], variants[15], variants[16], variants[17], variants[18], variants[19], variants[20], variants[21], variants[22], variants[23], variants[24], variants[25], variants[26], variants[27], variants[28], variants[29], variants[30]]}}]
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            encoded = json.dumps(payload, ensure_ascii=False)
            digest = report.canonical_payload_digest(payload)
            text = report.render_report(payload, digest).decode()
            raw_tokens = (
                "report-basic-secret", "report-digest-secret", "report-user", "report-realm", "report-response",
                "report-lf-secret", "report-crlf-secret", "report-fold-user", "report-fold-realm", "report-fold-response",
                "report-basic-redacted-fold-secret", "report-digest-redacted-fold-secret", "report-proxy-redacted-fold-secret",
                "report-proxy-bearer-secret", "report-proxy-basic-secret", "report-proxy-digest-secret", "report-api-key-secret",
                "report-redacted-tail-secret", "report-digest-redacted-tail-secret", "report-proxy-redacted-tail-secret",
                "report-prefix-secret", "report-digest-prefix-secret", "report-proxy-prefix-secret",
                "report-basic-cr-secret", "report-digest-cr-secret", "report-bearer-cr-secret",
                "report-proxy-basic-cr-secret", "report-proxy-digest-cr-secret", "report-proxy-bearer-cr-secret",
                "report-digest-cr-folded", "report-proxy-digest-cr-folded",
                "report-basic-redacted-cr-sentinel", "report-digest-redacted-cr-sentinel", "report-bearer-redacted-cr-sentinel",
                "report-proxy-basic-redacted-cr-sentinel", "report-proxy-digest-redacted-cr-sentinel", "report-proxy-bearer-redacted-cr-sentinel",
            )
            for value in raw_tokens:
                self.assertNotIn(value, encoded)
                self.assertNotIn(value, text)
            for marker in ("Authorization: Basic [redacted]", "Authorization: Digest [redacted]",
                           "Proxy-Authorization: Bearer [redacted]", "Proxy-Authorization: Basic [redacted]",
                           "Proxy-Authorization: Digest [redacted]", "X-Api-Key: [redacted]"):
                self.assertIn(marker, encoded)
                self.assertIn(marker, text)
            self.assertIn("next-line", encoded)
            self.assertIn("next-line", text)
            for safe in ("Authorization: Basic [redacted]", "Authorization: Digest [redacted]",
                         "Proxy-Authorization: Basic [redacted]", "Proxy-Authorization: Digest [redacted]",
                         "Authorization: Bearer [redacted]", "Proxy-Authorization: Bearer [redacted]"):
                self.assertFalse(report.credential_bearing_text(safe))
                self.assertEqual(report._text(safe), safe)
            self.assertTrue(report.validate_report_bytes(text.encode(), digest, payload))
