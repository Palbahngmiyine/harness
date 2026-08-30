try:
    from .test_reportkit import *
except ImportError:
    from test_reportkit import *

class ReportSlice35Tests(HwahapReportTests):
    def test_report_credential_segments_cover_pua_and_boundary_rules(self) -> None:
            markers = ("\ue000", "\uf8ff", "\U000f0000", "\U00100000", "\ufffe", "\uffff",
                       "\x00", "\x1f", "\x7f", "\u200b", "\u200d", "\u2060")
            keys = ("CLIENT-SECRET", "github-token", "private key")
            operators = ("=", ":=", ":")
            values = [f"{keys[index % 3]}{operators[index % 3]}pre{marker}report-segment-canary{marker}post"
                      for index, marker in enumerate(markers)]
            values += ["CLIENT-SECRET=[redacted]\ue000report-segment-canary",
                       "github-token:=\uf8ffreport-segment-canary"]
            for value in values:
                with self.subTest(value=repr(value)):
                    cleaned = report._text(value)
                    self.assertNotIn("report-segment-canary", cleaned)
                    self.assertEqual(report._text(cleaned), cleaned)
            for value in ("secret handling", "token usage unavailable", "client-secretary=value", "tokenization=value"):
                self.assertFalse(report.credential_bearing_text(value))
            contract, run, units, events, digests = self.fixture()
            run["deferred_security"] = [{"summary": "segment probes", "reason": values[0],
                                          "next_action": "wait", "evidence": values}]
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            digest = report.canonical_payload_digest(payload)
            data = report.render_report(payload, digest)
            self.assertNotIn("report-segment-canary", json.dumps(payload, ensure_ascii=False))
            self.assertNotIn("report-segment-canary", data.decode())
            self.assertTrue(report.validate_report_bytes(data, digest, payload))
            for fragment in (
                    "CLIENT-SECRET:<span></span>report-inline-canary",
                    "github-token:<span><small></small></span>report-inline-canary"):
                with self.subTest(fragment=fragment):
                    injected = data.replace(b"</main>", (fragment + "</main>").encode())
                    with self.assertRaisesRegex(ValueError, "credential-bearing"):
                        report.validate_report_bytes(injected, digest, payload)
            for fragment in ("CLIENT-SECRET:<div>report-block-canary</div>",
                             "github-token:<p>report-block-canary</p>",
                             "private key:<br>report-block-canary"):
                injected = data.replace(b"</main>", (fragment + "</main>").encode())
                self.assertTrue(report.validate_report_bytes(injected, digest, payload))
            attrs = data.replace(b"</main>", b'<div class="CLIENT-SECRET:" aria-live="report-attr-canary"></div></main>')
            self.assertTrue(report.validate_report_bytes(attrs, digest, payload))
            escaped = data.replace(b"</main>", b"&lt;div&gt;CLIENT-SECRET=report-escaped-canary&lt;/div&gt;</main>")
            with self.assertRaisesRegex(ValueError, "credential-bearing"):
                report.validate_report_bytes(escaped, digest, payload)
            raw = data.replace(b"</main>", b'<p class="CLIENT-SECRET=report-raw-canary"></p></main>')
            with self.assertRaisesRegex(ValueError, "credential-bearing"):
                report.validate_report_bytes(raw, digest, payload)

class ReportSlice36Tests(HwahapReportTests):
    def test_header_credential_whitespace_has_state_report_parity(self) -> None:
            whitespace = ("", " ", "\t", "\n", "\r", "\r\n", "\f", "\v", "\u00a0",
                          "\u2028", "\u2029", "\x1f")
            keys = ("private-key", "private key", "x-api-key", "x api key", "x_api_key",
                    "cookie", "authorization", "proxy-authorization")
            operators = ("=", ":=", ":")
            canary = "parity-header-canary"
            end_to_end = []
            for key in keys:
                separator = next((item for item in ("-", " ", "_") if item in key), None)
                for operator in operators:
                    for gap in whitespace:
                        variants = [f"{key}{gap}{operator}{canary}",
                                    f"{key}{operator}{gap}{canary}",
                                    f"{key}{operator}pre{gap}{canary}{gap}post"]
                        if separator:
                            variants.append(f"{key.replace(separator, gap, 1)}{operator}{canary}")
                        for value in variants:
                            state_result = state.credential_bearing_text(value)
                            report_result = report.credential_bearing_text(value)
                            self.assertEqual(state_result, report_result, repr(value))
                            if state_result and canary not in report._text(value):
                                end_to_end.append(value)
            contract, run, units, events, digests = self.fixture()
            run["deferred_security"] = [{"summary": "header parity", "reason": end_to_end[0],
                                          "next_action": "wait", "evidence": end_to_end[:24]}]
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            digest = report.canonical_payload_digest(payload)
            data = report.render_report(payload, digest)
            self.assertNotIn(canary, json.dumps(payload, ensure_ascii=False))
            self.assertNotIn(canary, data.decode())
            self.assertTrue(report.validate_report_bytes(data, digest, payload))
            attrs = data.replace(b"</main>", b'<div class="Private-Key:" aria-live="allowed"></div></main>')
            self.assertTrue(report.validate_report_bytes(attrs, digest, payload))
