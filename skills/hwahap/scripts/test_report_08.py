try:
    from .test_reportkit import *
except ImportError:
    from test_reportkit import *

class ReportSlice16Tests(HwahapReportTests):
    def test_completed_run_improvement_candidates_are_allowlisted_and_visible(self) -> None:
            contract, run, units, events, digests = self.fixture()
            run["improvement_candidates"] = [{
                "status": "proposed", "summary": "sentinel summary", "evidence": ["sentinel evidence", "Authorization: Bearer candidate-secret"],
                "expected_effect": "sentinel effect", "next_action": "sentinel next action",
                "command": "forbidden-command-sentinel", "path": "forbidden-path-sentinel", "unit_id": "forbidden-unit-sentinel",
            }]
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            candidate = payload["improvement-candidates"][0]
            self.assertEqual(set(candidate), set(report.IMPROVEMENT_CANDIDATE_FIELDS))
            self.assertEqual(candidate["status"], "proposed")
            encoded = json.dumps(payload, ensure_ascii=False)
            digest = report.canonical_payload_digest(payload)
            data = report.render_report(payload, digest)
            text = data.decode()
            self.assertTrue(report.validate_report_bytes(data, digest, payload))
            for value in ("sentinel summary", "sentinel evidence", "sentinel effect", "sentinel next action"):
                self.assertIn(value, encoded)
                self.assertIn(value, text)
            for value in ("forbidden-command-sentinel", "forbidden-path-sentinel", "forbidden-unit-sentinel"):
                self.assertNotIn(value, encoded)
                self.assertNotIn(value, text)
            self.assertNotIn("candidate-secret", encoded)
            self.assertNotIn("candidate-secret", text)
            self.assertIn("Authorization: Bearer [redacted]", text)
            self.assertIn('id="improvement-candidates"', text)
            self.assertIn("보고 전용 · 사용자 승인 전에는 실행하지 않음", text)
            self.assertIn(digest, text)

class ReportSlice17Tests(HwahapReportTests):
    def test_report_preserves_long_text_and_complete_histories(self) -> None:
            contract, run, units, _, digests = self.fixture()
            long_text = "x" * 400 + "-end-sentinel"
            units[0]["test_receipts"] = [{"test_id": f"receipt-{index}"} for index in range(1, 101)] + [{"test_id": "receipt-101-sentinel"}]
            units[0]["review_history"] = [{"round": index, "changed_paths": [f"review-{index}"]} for index in range(1, 101)] + [{"round": 101, "changed_paths": ["review-101-sentinel"]}]
            units[0]["improvement_history"] = [{"after_round": index, "action": f"improvement-{index}"} for index in range(1, 101)] + [{"after_round": 101, "action": "improvement-101-sentinel"}]
            run["goal_link"]["history"] = [{"reason": f"goal-history-{index}"} for index in range(1, 101)] + [{"reason": "goal-history-101-sentinel"}]
            run["improvement_candidates"] = [{"summary": f"candidate-{index}"} for index in range(1, 101)] + [{"summary": "candidate-101-sentinel"}]
            run["deviations"] = [{"summary": f"deviation-{index}"} for index in range(1, 101)] + [{"summary": long_text}]
            run["deferred_security"] = [{"summary": f"deferred-{index}"} for index in range(1, 101)] + [{"summary": "deferred-101-sentinel"}]
            run["final_review"]["attempts"] = [{"thread_id": f"attempt-{index}"} for index in range(1, 21)] + [{"thread_id": "attempt-21-sentinel"}]
            events = [{"sequence": index, "entity": "event", "from": "before", "to": "after", "reason": f"event-{index}"} for index in range(1, 501)] + [{"sequence": 501, "entity": "event", "from": "before", "to": "after", "reason": "event-501-sentinel"}]

            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            digest = report.canonical_payload_digest(payload)
            text = report.render_report(payload, digest).decode()
            parsed = json.loads(report.canonical_payload_bytes(payload))

            self.assertEqual(len(parsed["deviations"]["items"]), 101)
            self.assertEqual(payload["deviations"]["items"][-1]["summary"], long_text)
            self.assertEqual(len(payload["deviations"]["items"][-1]["summary"]), len(long_text))
            self.assertEqual(len(payload["units"][0]["test_receipts"]), 101)
            self.assertEqual(len(payload["units"][0]["review_history"]), 101)
            self.assertEqual(len(payload["units"][0]["improvement_history"]), 101)
            self.assertEqual(len(payload["provenance"]["goal_link"]["history"]), 101)
            self.assertEqual(len(payload["improvement-candidates"]), 101)
            self.assertEqual(len(payload["deviations"]["deferred_security"]), 101)
            self.assertEqual(len(payload["reviews"]["final_review"]["attempts"]), 21)
            self.assertEqual(len(parsed["timeline"]), 501)
            for sentinel in ("receipt-101-sentinel", "review-101-sentinel", "improvement-101-sentinel",
                             "goal-history-101-sentinel", "candidate-101-sentinel", long_text,
                             "deferred-101-sentinel", "attempt-21-sentinel", "event-501-sentinel"):
                self.assertIn(sentinel, json.dumps(parsed, ensure_ascii=False))
                self.assertIn(sentinel, text)
            self.assertTrue(report.validate_report_bytes(text.encode(), digest, payload))

class ReportSlice18Tests(HwahapReportTests):
    def test_validator_requires_improvement_candidates_section(self) -> None:
            contract, run, units, events, digests = self.fixture()
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            digest = report.canonical_payload_digest(payload)
            data = report.render_report(payload, digest).replace(b'id="improvement-candidates"', b'id="missing-improvement-candidates"')
            with self.assertRaisesRegex(ValueError, "missing report section: improvement-candidates"):
                report.validate_report_bytes(data, digest, payload)
