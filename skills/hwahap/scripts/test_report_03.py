try:
    from .test_reportkit import *
except ImportError:
    from test_reportkit import *

class ReportSlice6Tests(HwahapReportTests):
    def test_diff_snapshots_are_allowlisted_and_visible(self) -> None:
            contract, run, units, events, digests = self.fixture()
            snapshot = {"base_commit": "a" * 40, "target_commit": "b" * 40,
                        "base_tree": "c" * 40, "target_tree": "d" * 40,
                        "diff_digest": "sha256:" + "e" * 64, "changed_paths": ["snapshot-path"]}
            review = {"round": 1, "diff_snapshot": {**snapshot, "hostile": "drop-review"},
                      "verifier": {}, "scope_reviewer": {}}
            units[0]["review_history"] = [review]
            units[0]["test_receipts"] = [{"test_id": "receipt", "diff_snapshot": {**snapshot, "hostile": "drop-receipt"}}]
            run["final_review"]["attempts"][0]["diff_snapshot"] = {**snapshot, "hostile": "drop-final"}
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            self.assertEqual(payload["reviews"]["units"][0]["history"][0]["diff_snapshot"], snapshot)
            self.assertEqual(payload["tests-metrics"]["test_receipts"][0]["receipts"][0]["diff_snapshot"], snapshot)
            self.assertEqual(payload["reviews"]["final_review"]["attempts"][0]["diff_snapshot"], snapshot)
            encoded = json.dumps(payload, ensure_ascii=False)
            text = report.render_report(payload, report.canonical_payload_digest(payload)).decode()
            for value in snapshot.values():
                for marker in value if isinstance(value, list) else (value,):
                    self.assertIn(marker, encoded)
                    self.assertIn(marker, text)
            self.assertNotIn("drop-review", encoded + text)
            self.assertNotIn("drop-receipt", encoded + text)
            self.assertNotIn("drop-final", encoded + text)
            self.assertTrue(report.validate_report_bytes(text.encode(), report.canonical_payload_digest(payload), payload))

class ReportSlice7Tests(HwahapReportTests):
    def test_review_table_snapshot_column_matches_header(self) -> None:
            contract, run, units, events, digests = self.fixture()
            units[0]["review_history"] = [{"round": 1, "outcome": "pass", "verifier": {}, "scope_reviewer": {}}]
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            text = report.render_report(payload, report.canonical_payload_digest(payload)).decode()
            parser = _ReviewTableParser()
            parser.feed(text[text.index('<section id="reviews">'):text.index('<section id="scope-audit">')])
            self.assertEqual(len(parser.rows[0]), 9)
            self.assertTrue(all(len(row) == len(parser.rows[0]) for row in parser.rows[1:]))
            empty_payload = report.build_payload("/tmp/work", contract, run, self.fixture()[2], events, digests)
            empty = report.render_report(empty_payload, report.canonical_payload_digest(empty_payload)).decode()
            empty_parser = _ReviewTableParser()
            empty_parser.feed(empty[empty.index('<section id="reviews">'):empty.index('<section id="scope-audit">')])
            self.assertEqual(empty_parser.rows[1][0][1], "9")

class ReportSlice8Tests(HwahapReportTests):
    def test_scope_audit_is_allowlisted_and_visible(self) -> None:
            contract, run, units, events, digests = self.fixture()
            audit = {"authority": "attacker-value", "affects_gate": True,
                     "source_diff_digest": "sha256:" + "a" * 64,
                     "contract_lock_sha256": "sha256:" + "b" * 64, "hostile": "omit", "paths": [{
                         "path": "src", "contract_allowed": True, "passed_unit_covered": True,
                         "forbidden_overlap": False, "matched_contract_rules": ["src"],
                         "covering_passed_units": [{"unit_id": "u", "matched_rules": ["src"]}],
                         "matched_forbidden_rules": [], "verdict": "pass",
                         "evidence": {"diff_digest": "sha256:" + "a" * 64,
                                      "contract_lock_sha256": "sha256:" + "b" * 64,
                                      "passed_unit_ids": ["u"], "hostile": "omit"},
                         "hostile": "omit"}]}
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests, audit)
            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(payload["scope_audit"]["authority"], "derived-report-only")
            self.assertNotIn("hostile", json.dumps(payload, ensure_ascii=False))
            text = report.render_report(payload, report.canonical_payload_digest(payload)).decode()
            self.assertIn('id="scope-audit"', text)
            self.assertIn("src", text)
            self.assertTrue(report.validate_report_bytes(text.encode(), report.canonical_payload_digest(payload), payload))
