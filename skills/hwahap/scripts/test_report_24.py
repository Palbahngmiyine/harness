try:
    from .test_reportkit import *
except ImportError:
    from test_reportkit import *


class HwahapReportHandoffTests(HwahapReportTests):
    def aligned_payload(self):
        contract, run, units, events, digests = self.fixture()
        handoff = {"schema": "align-goal/v1", "revision": 1,
            "spec_digest": "sha256:" + "1" * 64,
            "specifications": [{"id": "S1", "statement": "emit report"}],
            "acceptance_checks": [{"id": "A1", "spec_ids": ["S1"]}],
            "implementation_units": [{"id": "U1", "spec_ids": ["S1"],
                                      "acceptance_ids": ["A1"]}],
            "confirmation": {"confirmed_at": "now",
                             "response_hash": "sha256:" + "2" * 64}}
        contract["spec"].update({"status": "align-goal", "handoff": handoff})
        units[0]["source_trace"] = {"unit_id": "U1", "spec_ids": ["S1"],
                                     "acceptance_ids": ["A1"]}
        return report.build_payload("/tmp/work", contract, run, units, events, digests)

    def assert_invalid(self, payload):
        data = report.canonical_payload_bytes(payload)
        digest = report.canonical_payload_digest(payload)
        with self.assertRaises(ValueError):
            report.validate_report_data_bytes(data, payload, digest)

    def test_payload_and_html_preserve_source_handoff_and_unit_trace(self):
        payload = self.aligned_payload()
        data = report.canonical_payload_bytes(payload)
        digest = report.canonical_payload_digest(payload)
        self.assertTrue(report.validate_report_data_bytes(data, payload, digest))
        html = report.render_report(payload, digest).decode()
        self.assertIn("align-goal source", html)
        self.assertEqual(payload["contract"]["spec"]["handoff"]["schema"],
                         "align-goal/v1")
        self.assertEqual(payload["units"][0]["source_trace"]["unit_id"], "U1")

    def test_fidelity_gate_rejects_missing_mismatched_and_duplicate_trace(self):
        payload = self.aligned_payload()
        missing = copy.deepcopy(payload); missing["contract"]["spec"].pop("handoff")
        mismatch = copy.deepcopy(payload); mismatch["units"][0]["source_trace"]["spec_ids"] = []
        duplicate = copy.deepcopy(payload); duplicate["units"].append(copy.deepcopy(duplicate["units"][0]))
        for value in (missing, mismatch, duplicate):
            with self.subTest(value=value):
                self.assert_invalid(value)

    def test_non_success_terminal_keeps_handoff_without_claiming_full_coverage(self):
        payload = self.aligned_payload()
        payload["summary"]["status"] = "failed"; payload["units"] = []
        data = report.canonical_payload_bytes(payload)
        digest = report.canonical_payload_digest(payload)
        self.assertTrue(report.validate_report_data_bytes(data, payload, digest))
        self.assertIn("handoff", payload["contract"]["spec"])


if __name__ == "__main__":
    unittest.main()
