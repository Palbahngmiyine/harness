try:
    from .test_reportkit import *
except ImportError:
    from test_reportkit import *

class ReportSlice4Tests(HwahapReportTests):
    def test_human_summary_precedes_collapsed_complete_evidence(self) -> None:
            contract, run, units, events, digests = self.fixture()
            run["deviations"] = [{"summary": "문제", "root_cause": "원인", "impact": "이전 영향",
                                  "prevention": "적용한 개선", "evidence_explanation": "근거가 개선을 검증",
                                  "evidence": ["검증 근거"]}]
            run["deferred_security"] = [{"summary": "남은 위험", "reason": "미검증",
                                         "next_action": "사용자 결정", "evidence": ["경계"]}]
            run["improvement_candidates"] = [{"status": "proposed", "summary": "후속 후보",
                                               "evidence": ["검토"], "expected_effect": "기대 효과",
                                               "next_action": "다음 결정"}]
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            digest = report.canonical_payload_digest(payload)
            text = report.render_report(payload, digest).decode()
            ordered = ("summary", "deviations", "improvement-candidates", "next-actions", "tests-metrics",
                       "evidence-vault", "contract", "agents", "units", "timeline", "reviews", "scope-audit",
                       "failures-recovery", "provenance", "report-data")
            positions = [text.index(f'id="{identifier}"') for identifier in ordered]
            self.assertEqual(positions, sorted(positions))
            self.assertNotIn('id="evidence-vault" class="evidence-vault" open', text)
            self.assertIn('class="change-card panel md-card md-card-filled"', text)
            self.assertIn('class="risk-card tile md-card md-card-filled"', text)
            self.assertIn('class="proposal-card tile md-card md-card-filled"', text)
            for phrase in ("이전 문제", "발생 원인", "적용한 개선", "이전 대비 기대 변화",
                           "아직 남은 위험", "기대 효과", "다음 결정", "실제 운영 효과를 보장"):
                self.assertIn(phrase, text)
            self.assertIn("이전 문제”가 다시 발생하기 전에 “적용한 개선", text)
            self.assertIn("min-block-size:48px", text)
            self.assertIn("outline:3px solid var(--md-sys-color-primary)", text)
            self.assertIn("details>summary:focus-visible::after{opacity:var(--md-sys-state-focus-opacity)}", text)
            self.assertIn('<caption>정본 report-data.json ledger', text)
            self.assertTrue(report.validate_report_bytes(text.encode(), digest, payload))

class ReportSlice5Tests(HwahapReportTests):
    def test_provenance_values_are_visible_in_payload_and_html(self) -> None:
            contract, run, units, events, digests = self.fixture()
            spec = {"source": "spec-source-sentinel", "sha256": "spec-sha-sentinel", "confirmed_at": "spec-confirmed-sentinel"}
            contract["spec"] = spec
            final_digests = ("sha256:" + "1" * 64, "sha256:" + "2" * 64)
            run.update({
                "fast_status": "fast-status-sentinel",
                "final_review": {"status": "pass", "attempts": [
                    {"model": "sol", "effort": "ultra", "status": "pass", "thread_id": "attempt-one", "diff_digest": final_digests[0]},
                    {"model": "sol", "effort": "xhigh", "status": "unavailable", "thread_id": "attempt-two", "diff_digest": final_digests[1]},
                ]},
                "goal_link": {"current": {
                    "thread_id": "goal-thread-sentinel", "receipt_sha256": "goal-receipt-sentinel",
                    "objective_sha256": "goal-objective-sentinel", "observed_at": "goal-observed-sentinel",
                    "token_total": 987654, "source": "goal-source-sentinel", "mode": "goal-mode-sentinel",
                    "completion_sync": "goal-sync-sentinel", "sync_result": "goal-result-sentinel",
                    "reason": "Authorization: Bearer provenance-secret",
                }, "history": []},
            })
            digests = {"contract-sentinel": "sha256:" + "3" * 64, "events-sentinel": "sha256:" + "4" * 64}
            run["agent_profiles"] = {"sol-sentinel.toml": "sha256:" + "5" * 64, "luna-sentinel.toml": "sha256:" + "6" * 64}
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            encoded = json.dumps(payload, ensure_ascii=False)
            text = report.render_report(payload, report.canonical_payload_digest(payload)).decode()
            sentinels = (
                "fast-status-sentinel", *final_digests, "goal-thread-sentinel", "goal-receipt-sentinel",
                "goal-objective-sentinel", "goal-observed-sentinel", "987654", "goal-source-sentinel",
                "goal-mode-sentinel", "goal-sync-sentinel", "goal-result-sentinel", "spec-source-sentinel",
                "spec-sha-sentinel", "spec-confirmed-sentinel", "contract-sentinel", "events-sentinel",
                "sha256:" + "3" * 64, "sha256:" + "4" * 64, "sol-sentinel.toml", "luna-sentinel.toml",
                "sha256:" + "5" * 64, "sha256:" + "6" * 64,
            )
            for value in sentinels:
                self.assertIn(value, encoded)
                self.assertIn(value, text)
            self.assertNotIn("provenance-secret", encoded)
            self.assertNotIn("provenance-secret", text)
            self.assertIn("Authorization: Bearer [redacted]", encoded)
            self.assertTrue(report.validate_report_bytes(text.encode(), report.canonical_payload_digest(payload), payload))
