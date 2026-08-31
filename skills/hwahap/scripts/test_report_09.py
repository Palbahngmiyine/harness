try:
    from .test_reportkit import *
except ImportError:
    from test_reportkit import *

class ReportSlice19Tests(HwahapReportTests):
    def test_escape_redact_paths_and_exclude_unknown_values(self) -> None:
            contract, run, units, events, digests = self.fixture()
            units[0]["review_history"] = [{"round": 1, "changed_paths": ["/outside/file"], "outcome": "fail",
                                            "verifier": {"evidence": ["password=hunter2", "Authorization: Bearer topsecret", "-----BEGIN PRIVATE KEY-----abc-----END PRIVATE KEY-----", "https://user:pass@example.invalid/x"], "unknown_nested": "omit"}, "scope_reviewer": {}}]
            units[0]["improvement_history"] = [{"after_round": 1, "kind": "terra_recovery", "root_cause": "cause", "hypothesis": "hypothesis", "action": "action", "evidence": ["proof"]}]
            run["deviations"] = [{"summary": "drift", "root_cause": "cause", "impact": "impact",
                                   "prevention": "prevention", "evidence_explanation": "evidence explains prevention",
                                   "evidence": ["bounded evidence"]}]
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            digest = report.canonical_payload_digest(payload)
            data = report.render_report(payload, digest).decode()
            self.assertIn("$WORKSPACE", data)
            self.assertIn("[external reference]", data)
            self.assertIn("&lt;script&gt;", data)
            self.assertIn("password=[redacted]", data)
            self.assertIn("Authorization: Bearer [redacted]", data)
            self.assertNotIn("topsecret", data)
            self.assertNotIn("PRIVATE KEY-----abc", data)
            self.assertNotIn("user:pass@", data)
            self.assertNotIn("unknown_nested", data)
            self.assertNotIn("do not include", data)
            self.assertNotIn("ignore this", data)
            self.assertNotIn("raw_log", data)
            self.assertIn("[redacted credential URL]", data)
            self.assertIn("root_cause=cause", data)
            self.assertIn("hypothesis=hypothesis", data)
            self.assertIn("next", data)

class ReportSlice20Tests(HwahapReportTests):
    def test_payload_digest_is_canonical_and_validator_rejects_bad_report(self) -> None:
            contract, run, units, events, digests = self.fixture()
            one = report.build_payload("/tmp/work", contract, run, units, events, digests)
            two = copy.deepcopy(one)
            two = {key: two[key] for key in reversed(list(two))}
            self.assertEqual(report.canonical_payload_digest(one), report.canonical_payload_digest(two))
            with self.assertRaises(ValueError):
                report.validate_report_bytes(b"<main id=\"report\"></main>", "sha256:" + "e" * 64, one)

class ReportSlice21Tests(HwahapReportTests):
    def test_report_data_ledger_is_visible_complete_and_bound(self) -> None:
            contract, run, units, events, digests = self.fixture()
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            payload["ledger-probe"] = {"a/b": "", "~key": 7, "flag": True, "none": None, "empty": [], "obj": {}}
            digest = report.canonical_payload_digest(payload)
            data = report.render_report(payload, digest)
            text = data.decode()
            self.assertIn("/ledger-probe/a~1b", text)
            self.assertIn("/ledger-probe/~0key", text)
            for literal in ('&quot;&quot;', "7", "true", "null", "[]", "{}"):
                self.assertIn(literal, text)
            self.assertNotIn('application/json', text)
            self.assertNotIn('#report-data{display:none', text)
            self.assertNotIn('.evidence-content{display:none', text)
            self.assertIn('<details id="evidence-vault" class="evidence-vault">', text)
            self.assertTrue(report.validate_report_bytes(data, digest, payload))
            block = report._payload_ledger_block(payload).encode()
            with self.assertRaises(ValueError):
                report.validate_report_bytes(data.replace(block, b"", 1), digest, payload)
            with self.assertRaises(ValueError):
                report.validate_report_bytes(data.replace(b"/ledger-probe/a~1b", b"/ledger-probe/changed", 1), digest, payload)
            with self.assertRaises(ValueError):
                report.validate_report_bytes(data.replace(b"</main>", block + b"</main>"), digest, payload)
            changed = copy.deepcopy(payload)
            changed["ledger-probe"]["none"] = "changed"
            with self.assertRaises(ValueError):
                report.validate_report_bytes(data, digest, changed)
