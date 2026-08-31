try:
    from .test_reportkit import *
except ImportError:
    from test_reportkit import *


class ReportSlice46Tests(HwahapReportTests):
    def test_decisions_and_completion_explain_evidence_with_5w3h(self) -> None:
        contract, run, units, events, digests = self.fixture()
        diff_digest = "sha256:" + "9" * 64
        snapshot = {"diff_digest": diff_digest, "changed_paths": ["src"]}
        units[0]["review_history"] = [{"round": 1, "outcome": "pass", "diff_digest": diff_digest,
            "diff_snapshot": snapshot, "verifier": {"model": "gpt-5.6-luna", "status": "pass", "diff_digest": diff_digest,
            "evidence": ["focused regression PASS"]}, "scope_reviewer": {"model": "gpt-5.6-terra", "status": "pass",
            "diff_digest": diff_digest, "evidence": ["same snapshot scope PASS"]}}]
        run["metrics"]["test_runs"] = 4
        run["final_review"] = {"status": "pass", "attempts": [{"model": "gpt-5.6-sol", "status": "pass",
            "diff_digest": diff_digest, "diff_snapshot": snapshot, "evidence": ["0 blocking findings"]}]}
        context = {"scenario": "외부 감사자가 JSON actor를 실제 작성자 신원으로 믿는 상황", "affected_scope": "외부로 공유된 완료 receipt와 승인 기록",
                   "impact": "서명이 없으면 위조된 actor와 실제 actor를 구분할 수 없음", "decision_reason": "로컬 신뢰만 필요한지 서명된 외부 증명이 필요한지는 사용자가 정해야 함",
                   "evidence_relation": "trust boundary 문구는 서명 검증이 없다는 현재 경계만 뒷받침함", "success_condition": "변조된 서명을 거부하고 모든 actor receipt의 서명을 검증함"}
        run["deferred_security"] = [{"summary": "외부 신원 증명", "reason": "actor 신원 서명 미검증", "next_action": "서명 receipt 계약 결정", "evidence": ["documented trust boundary"], "decision_context": context}]
        run["improvement_candidates"] = [{"status": "proposed", "summary": "후속 후보", "expected_effect": "오용 방지", "next_action": "사용자 승인", "evidence": ["final Ultra report"], "decision_context": context}]
        run["deviations"] = [{"summary": "보고서 누락", "impact": "값을 읽을 수 없음", "root_cause": "수동 목록", "prevention": "ledger 자동 출력", "evidence": ["payload-ledger binding tests"], "evidence_explanation": "ledger 변조 회귀가 누락된 값을 탐지하는지 확인함"}]
        payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
        digest = report.canonical_payload_digest(payload)
        text = report.render_report(payload, digest).decode()
        for label in ("누가 (Who)", "언제 (When)", "어디서 (Where)", "무엇을 (What)", "왜 (Why)", "어떻게 (How)", "얼마나 (How much)", "얼마 동안 (How long)"):
            self.assertIn(label, text)
        for evidence in ("payload-ledger binding tests", "documented trust boundary", "final Ultra report", "focused regression PASS", "same snapshot scope PASS"):
            self.assertIn(evidence, text)
        self.assertTrue(report.validate_report_bytes(text.encode(), digest, payload))
