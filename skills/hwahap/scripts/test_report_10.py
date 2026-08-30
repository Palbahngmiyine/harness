try:
    from .test_reportkit import *
except ImportError:
    from test_reportkit import *

class ReportSlice22Tests(HwahapReportTests):
    def test_render_and_validate_share_safe_payload_boundary(self) -> None:
            contract, run, units, events, digests = self.fixture()
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            digest = report.canonical_payload_digest(payload)
            data = report.render_report(payload, digest)
            self.assertTrue(report.validate_report_bytes(data, digest, payload))
            bad_values = (
                {"client-secret": "renderer-boundary-canary"},
                {"Authorization": "Bearer renderer-boundary-canary"},
                {"client\u200bsecret": "dicp-boundary-canary"},
                {"/private/tmp/report-boundary-path": "safe"},
                {"nested": [{"X-Api-Key": "nested-boundary-canary"}]},
            )
            block = report._payload_ledger_block(payload).encode()
            for extra in bad_values:
                with self.subTest(extra=extra):
                    bad = copy.deepcopy(payload)
                    bad["boundary"] = extra
                    bad_digest = report.canonical_payload_digest(bad)
                    with self.assertRaises(report.HwahapReportError) as rendered:
                        report.render_report(bad, bad_digest)
                    self.assertEqual(str(rendered.exception), "report data is invalid")
                    self.assertNotIn("boundary-canary", str(rendered.exception))
                    crafted = data.replace(block, report._payload_ledger_block(bad).encode(), 1)
                    with self.assertRaises(report.HwahapReportError) as validated:
                        report.validate_report_bytes(crafted, bad_digest, bad)
                    self.assertEqual(str(validated.exception), "report data is invalid")
                    self.assertNotIn("boundary", str(validated.exception))

class ReportSlice23Tests(HwahapReportTests):
    def test_canonical_payload_bytes_are_utf8_deterministic_and_exact(self) -> None:
            one = {"z": "한글 😀", "nested": {"b": 2, "a": ["값"]}}
            two = {"nested": {"a": ["값"], "b": 2}, "z": "한글 😀"}
            encoded = report.canonical_payload_bytes(one)
            self.assertEqual(encoded, report.canonical_payload_bytes(two))
            self.assertIn("한글 😀".encode("utf-8"), encoded)
            self.assertNotIn(b"\\u", encoded)
            self.assertNotIn(b"\n", encoded)
            digest = report.canonical_payload_digest(one)
            self.assertTrue(report.validate_report_data_bytes(encoded, two, digest))

class ReportSlice24Tests(HwahapReportTests):
    def test_report_data_validation_rejects_any_byte_or_digest_drift(self) -> None:
            payload = {"nested": {"value": "stable"}, "items": [1, 2]}
            encoded = report.canonical_payload_bytes(payload)
            digest = report.canonical_payload_digest(payload)
            for data, expected, expected_digest in (
                (encoded + b"\n", payload, digest),
                (encoded[:-1] + b"!", payload, digest),
                (b'{"items":[1,2]}', payload, digest),
                (encoded, payload, "sha256:" + "f" * 64),
                (b"\xff", payload, digest),
                (b"not-json", payload, digest),
            ):
                with self.subTest(data=data, expected_digest=expected_digest):
                    with self.assertRaisesRegex(report.HwahapReportError, "report data is invalid"):
                        report.validate_report_data_bytes(data, expected, expected_digest)

class ReportSlice25Tests(HwahapReportTests):
    def test_report_data_rejects_nonfinite_credentials_and_paths_generically(self) -> None:
            for value in (float("nan"), float("inf"), float("-inf")):
                with self.subTest(value=value):
                    with self.assertRaisesRegex(report.HwahapReportError, "report data is invalid"):
                        report.canonical_payload_bytes({"nested": {"value": value}})
            contract, run, units, events, digests = self.fixture()
            canary = "Authorization: Digest username=payload-secret"
            contract["goal"] = canary
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            encoded = report.canonical_payload_bytes(payload)
            self.assertNotIn(b"payload-secret", encoded)
            self.assertTrue(report.validate_report_data_bytes(encoded, payload, report.canonical_payload_digest(payload)))
            for unsafe in ({"evidence": canary}, {"source": "/private/tmp/work/credential-canary.txt"}):
                with self.assertRaisesRegex(report.HwahapReportError, "report data is invalid") as raised:
                    report.validate_report_data_bytes(report.canonical_payload_bytes(unsafe), unsafe,
                                                      report.canonical_payload_digest(unsafe))
                self.assertNotIn("payload-secret", str(raised.exception))
                self.assertNotIn("credential-canary", str(raised.exception))
