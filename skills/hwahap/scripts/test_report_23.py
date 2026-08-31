try:
    from .test_reportkit import *
except ImportError:
    from test_reportkit import *


class ReportSlice47Tests(HwahapReportTests):
    def _deviation(self) -> dict:
        return {
            "summary": "finding", "root_cause": "manual list",
            "impact": "report omitted a field", "prevention": "canonical validation",
            "evidence_explanation": "the focused check proves prevention catches omission",
            "evidence": ["focused regression"],
        }

    def test_build_rejects_non_exact_v4_deviations(self) -> None:
        contract, run, units, events, digests = self.fixture()
        valid = self._deviation()
        cases = [
            {"summary": "missing fields"},
            valid | {"stale": "field"},
            valid | {"evidence_explanation": ""},
            valid | {"evidence": []},
        ]
        for value in cases:
            with self.subTest(value=value):
                run["deviations"] = [value]
                with self.assertRaisesRegex(ValueError, "deviations"):
                    report.build_payload("/tmp/work", contract, run, units, events, digests)

    def test_report_data_and_html_validation_reject_non_exact_v4(self) -> None:
        contract, run, units, events, digests = self.fixture()
        run["deviations"] = [self._deviation()]
        payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
        data = report.render_report(payload, report.canonical_payload_digest(payload))
        malformed = copy.deepcopy(payload)
        malformed["deviations"]["items"][0].pop("evidence_explanation")
        digest = report.canonical_payload_digest(malformed)
        with self.assertRaises(ValueError):
            report.validate_report_data_bytes(report.canonical_payload_bytes(malformed), malformed, digest)
        with self.assertRaises(ValueError):
            report.validate_report_bytes(data, digest, malformed)

    def test_evidence_explanation_is_visible_and_causally_ordered(self) -> None:
        contract, run, units, events, digests = self.fixture()
        run["deviations"] = [self._deviation()]
        payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
        digest = report.canonical_payload_digest(payload)
        rendered = report.render_report(payload, digest).decode()
        vault = rendered.index('id="evidence-vault"')
        for value in ("manual list", "canonical validation", "focused regression",
                      "the focused check proves prevention catches omission"):
            self.assertLess(rendered.index(value), vault)
        self.assertIn("왜 이 검사로 개선됐다고 판단했나", rendered)
        self.assertTrue(report.validate_report_bytes(rendered.encode(), digest, payload))
