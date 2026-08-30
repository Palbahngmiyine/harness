try:
    from .test_reportkit import *
except ImportError:
    from test_reportkit import *

class ReportSlice40Tests(HwahapReportTests):
    def test_prefixed_assignment_credentials_share_state_grammar_and_redaction(self) -> None:
            values = ("CLIENT-SECRET=report-assignment-sentinel", "github-token:=report-assignment-sentinel",
                      "service-password: report-assignment-sentinel", "client secret=report-assignment-sentinel",
                      "x-api-key=report-assignment-sentinel", "private key=report-assignment-sentinel",
                      "client-secret=\nreport-assignment-sentinel", "client-secret=\r\nreport-assignment-sentinel",
                      "client-secret=\rreport-assignment-sentinel", "client-secret=\\\nreport-assignment-sentinel",
                      "client\fsecret=report-assignment-sentinel", "client\vsecret=report-assignment-sentinel",
                      "client\u00a0secret=report-assignment-sentinel",
                      "client-secret=[redacted] report-assignment-sentinel",
                      "client-secret=[redacted]\r\n\tresponse=report-assignment-sentinel",
                      "CLIENT-SECRET=<report-assignment-sentinel>",
                      "github-token:=pre<report-assignment-sentinel>post",
                      "service-password:\"<report-assignment-sentinel>\"",
                      "client secret: <report-assignment-sentinel>",
                      "x-api-key=<report-assignment-sentinel>", "private key:=<report-assignment-sentinel>")
            for value in values:
                with self.subTest(value=value):
                    self.assertTrue(report.credential_bearing_text(value))
                    cleaned = report._text(value)
                    self.assertNotIn("report-assignment-sentinel", cleaned)
                    self.assertEqual(report._text(cleaned), cleaned)
            for value in ("secret handling", "token usage unavailable", "client-secretary=value", "tokenization=value"):
                self.assertFalse(report.credential_bearing_text(value))
                self.assertEqual(report._text(value), value)
            self.assertFalse(report.credential_bearing_text("client-secret=[redacted]"))
            self.assertEqual(report._text("client-secret=[redacted]"), "client-secret=[redacted]")
            contract, run, units, events, digests = self.fixture()
            run["deferred_security"] = [{"summary": "assignment probes", "reason": values[0],
                                          "next_action": "wait", "evidence": list(values)}]
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            encoded = json.dumps(payload, ensure_ascii=False)
            digest = report.canonical_payload_digest(payload)
            data = report.render_report(payload, digest)
            self.assertNotIn("report-assignment-sentinel", encoded)
            self.assertNotIn("report-assignment-sentinel", data.decode())
            self.assertTrue(report.validate_report_bytes(data, digest, payload))
            injected = data.replace(b'<main id="report">',
                                    b'<main id="report" class="CLIENT-SECRET=report-assignment-sentinel">')
            with self.assertRaises(ValueError):
                report.validate_report_bytes(injected, digest, payload)

class ReportSlice41Tests(HwahapReportTests):
    def test_shared_engine_maps_obfuscated_keys_and_overlapping_spans(self) -> None:
            marker = "credential-engine-canary"
            obfuscators = ("\u200b", "\ue000", "\ufffe", "\x1f", "\u2060", "\u2028", "\u2029")
            for key in ("CLIENT-SECRET", "github-token", "service-password", "private key"):
                for obfuscator in obfuscators:
                    with self.subTest(key=key, obfuscator=repr(obfuscator)):
                        raw_key = obfuscator.join(key)
                        value = f"{raw_key}{obfuscator}:={obfuscator}pre<{marker}>{obfuscator}post"
                        self.assertTrue(state.credential_bearing_text(value))
                        self.assertTrue(report.credential_bearing_text(value))
                        cleaned = report._text(value)
                        self.assertNotIn(marker, cleaned)
                        self.assertEqual(report._text(cleaned), cleaned)
            for value in ("secret handling", "token usage unavailable", "client-secretary=value", "😀 multilingual 텍스트"):
                self.assertFalse(state.credential_bearing_text(value))
                self.assertFalse(report.credential_bearing_text(value))

class ReportSlice42Tests(HwahapReportTests):
    def test_shared_engine_dual_views_cover_every_obfuscator_class(self) -> None:
            marker = "dual-view-canary"
            state._ensure_dependencies()
            engine = state._dependency_modules[1]
            codepoints = (0x00AD, 0x034F, 0x061C, 0x115F, 0x1160, 0x17B4, 0x17B5,
                          0x180B, 0x200B, 0x2028, 0x2029, 0x2060, 0x3164, 0xFE00,
                          0xFE0F, 0xFFA0, 0xE0100, 0x001F, 0xE000, 0xFDD0, 0xFFFE, 0x1FFFE)
            for codepoint in codepoints:
                separator = chr(codepoint)
                for key in (f"client{separator}secret", f"client-se{separator}cret"):
                    value = f"{key}{separator}:={separator}pre<{marker}>{separator}post"
                    with self.subTest(codepoint=hex(codepoint), key=key):
                        findings = engine.findings(value)
                        self.assertTrue(state.credential_bearing_text(value))
                        self.assertTrue(report.credential_bearing_text(value))
                        self.assertEqual(len(findings), len({(item.kind, item.start, item.end, item.value_start, item.value_end, item.scheme) for item in findings}))
                        self.assertNotIn(marker, report._text(value))
                        self.assertEqual(report._text(report._text(value)), report._text(value))
                        raw_payload = report.canonical_payload_bytes({"evidence": value})
                        with self.assertRaises(report.HwahapReportError):
                            report.validate_report_data_bytes(raw_payload, {"evidence": value}, report.canonical_payload_digest({"evidence": value}))
            for value in ("Authorization: Basic [redacted]", "Proxy-Authorization: Digest [redacted]",
                          "client-secret=[redacted]", "token_total=3", "😀 variation\ufe0f"):
                self.assertFalse(state.credential_bearing_text(value))
                self.assertFalse(report.credential_bearing_text(value))
