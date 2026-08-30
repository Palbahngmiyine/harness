try:
    from .test_reportkit import *
except ImportError:
    from test_reportkit import *

class ReportSlice37Tests(HwahapReportTests):
    def test_validator_rejects_extra_static_fragments(self) -> None:
            contract, run, units, events, digests = self.fixture()
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            digest = report.canonical_payload_digest(payload)
            data = report.render_report(payload, digest)
            fragments = (
                '<link rel="stylesheet" href="https://evil.invalid/injected.css">',
                '<script type="module">document.body.dataset.injected="1";</script>',
                f'<meta name="hwahap-source-sha256" content="{digest}">',
                '<section id="summary"></section>',
                '<style>body{display:none}</style>',
            )
            for fragment in fragments:
                with self.subTest(fragment=fragment):
                    injected = data.replace(b"</main>", (fragment + "</main>").encode())
                    with self.assertRaises(ValueError):
                        report.validate_report_bytes(injected, digest, payload)

class ReportSlice38Tests(HwahapReportTests):
    def test_escaped_user_markup_remains_valid_report_content(self) -> None:
            contract, run, units, events, digests = self.fixture()
            run["goal_link"]["current"]["reason"] = '<img src="safe"> <!-- harmless text -->'
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            digest = report.canonical_payload_digest(payload)
            data = report.render_report(payload, digest)
            text = data.decode()
            self.assertIn("&lt;img src=&quot;safe&quot;&gt;", text)
            self.assertIn("&lt;!-- harmless text --&gt;", text)
            self.assertTrue(report.validate_report_bytes(data, digest, payload))

class ReportSlice39Tests(HwahapReportTests):
    def test_curl_and_secret_assignments_are_redacted_in_payload_and_html(self) -> None:
            contract, run, units, events, digests = self.fixture()
            continuation = "curl " + chr(92) + "\n  --user audit:linecase URL"
            continuation_crlf = "curl " + chr(92) + "\r\n  --user audit:crlfcase URL"
            values = ("curl -u user:pass URL", "curl -uuser:pass URL", continuation,
                      continuation_crlf,
                      "curl --user user:pass", "curl --user=user:pass",
                      "curl -Uuser:pass URL", "curl --proxy-user user:pass",
                      "curl --proxy-user=user:pass", "curl --oauth2-bearer supersecret",
                      "curl --oauth2-bearer=supersecret", "SECRET_KEY=supersecret",
                      "SERVICE_SECRET_KEY:=supersecret")
            run["deviations"] = [{"summary": value, "root_cause": "context",
                                  "impact": "impact", "prevention": "prevention",
                                  "evidence": ["evidence"]} for value in values]
            run["improvement_candidates"] = [{"status": "proposed", "summary": value,
                                               "evidence": ["evidence"],
                                               "expected_effect": "effect",
                                               "next_action": "action"} for value in values]
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            encoded = json.dumps(payload, ensure_ascii=False)
            digest = report.canonical_payload_digest(payload)
            text = report.render_report(payload, digest).decode()
            for raw in ("user:pass", "supersecret", "audit:linecase", "audit:crlfcase"):
                self.assertNotIn(raw, encoded)
                self.assertNotIn(raw, text)
            for marker in ("curl -u [redacted] URL", "curl -u[redacted] URL",
                           "curl --user [redacted] URL",
                           "curl --user [redacted]", "curl --user=[redacted]",
                           "curl -U[redacted] URL", "curl --proxy-user [redacted]",
                           "curl --proxy-user=[redacted]", "curl --oauth2-bearer [redacted]",
                           "curl --oauth2-bearer=[redacted]", "SECRET_KEY=[redacted]",
                           "SERVICE_SECRET_KEY:=[redacted]"):
                self.assertIn(marker, encoded)
                self.assertIn(marker, text)
            self.assertTrue(report.validate_report_bytes(text.encode(), digest, payload))
            harmless = "curlish --user documentation"
            self.assertFalse(report.credential_bearing_text(harmless))
            self.assertEqual(report._text(harmless), harmless)
