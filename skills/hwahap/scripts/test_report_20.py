try:
    from .test_reportkit import *
except ImportError:
    from test_reportkit import *


class ReportSlice47Tests(HwahapReportTests):
    def test_missing_decision_context_is_reported_as_missing_not_filled_with_generic_claims(self) -> None:
        contract, run, units, events, digests = self.fixture()
        run["deferred_security"] = [{"summary": "외부 신원 증명", "reason": "서명 없음",
                                      "next_action": "정책 결정", "evidence": ["boundary"]}]
        payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
        text = report.render_report(payload, report.canonical_payload_digest(payload)).decode()
        self.assertIn("판단 설명 누락", text)
        self.assertIn("제목만으로 위험이나 후속 작업의 필요성을 판단할 수 없습니다", text)
        self.assertNotIn("위조된 actor", text)
