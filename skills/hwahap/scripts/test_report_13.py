try:
    from .test_reportkit import *
except ImportError:
    from test_reportkit import *

class ReportSlice31Tests(HwahapReportTests):
    def test_validator_rejects_credential_shaped_markup(self) -> None:
            contract, run, units, events, digests = self.fixture()
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            digest = report.canonical_payload_digest(payload)
            data = report.render_report(payload, digest)
            malformed = (
                "<div x-api-key=Basic secret></div>",
                "<Authorization:Basic>secret</Authorization:Basic>",
                "<div Authorization&#58;Basic=secret></div>",
                "<div class=Authorization:Basic=secret></div>",
                "<div class=ok x_api_key=Basic-secret></div>",
                "<div class=ok><x-api-key></div>",
                '<div class="one" class="two"></div>',
            )
            for fragment in malformed:
                with self.subTest(fragment=fragment):
                    injected = data.replace(b"</main>", (fragment + "</main>").encode())
                    with self.assertRaises(ValueError):
                        report.validate_report_bytes(injected, digest, payload)

class ReportSlice32Tests(HwahapReportTests):
    def test_validator_rejects_credentials_reconnected_across_text_nodes(self) -> None:
            contract, run, units, events, digests = self.fixture()
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            digest = report.canonical_payload_digest(payload)
            data = report.render_report(payload, digest)
            fragments = (
                "Authorization:<span></span> Basic auth-split-secret",
                "Proxy-Authorization: <span><span>Digest proxy-split-secret</span></span>",
                "X-Api-Key:<span></span> x-api-split-secret",
                "x_api_key=<span>Basic</span> x-under-split-secret",
                "Cookie:<span></span>cookie-split-secret",
                "Password:<span></span>password-split-secret",
                "Private-Key: <span></span>private-split-secret",
                "Bearer <span><span>bearer-split-secret</span></span>",
                "SECRET_<span></span>KEY=<span>assignment-split-secret</span>",
            )
            for fragment in fragments:
                with self.subTest(fragment=fragment):
                    injected = data.replace(b"</main>", (fragment + "</main>").encode())
                    with self.assertRaisesRegex(ValueError, "credential-bearing"):
                        report.validate_report_bytes(injected, digest, payload)

class ReportSlice33Tests(HwahapReportTests):
    def test_validator_keeps_block_and_line_break_boundaries(self) -> None:
            contract, run, units, events, digests = self.fixture()
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            digest = report.canonical_payload_digest(payload)
            data = report.render_report(payload, digest)
            for fragment in (
                "Authorization:<div>Basic block-split-secret</div>",
                "X-Api-Key:<br> x-api-line-split-secret",
            ):
                with self.subTest(fragment=fragment):
                    injected = data.replace(b"</main>", (fragment + "</main>").encode())
                    self.assertTrue(report.validate_report_bytes(injected, digest, payload))

class ReportSlice34Tests(HwahapReportTests):
    def test_validator_does_not_join_distinct_attribute_values(self) -> None:
            contract, run, units, events, digests = self.fixture()
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            digest = report.canonical_payload_digest(payload)
            data = report.render_report(payload, digest).replace(
                b"</main>", b'<div class="Authorization:" aria-live="Basic [redacted]"></div></main>'
            )
            self.assertTrue(report.validate_report_bytes(data, digest, payload))

    def test_receipt_heading_boundary_keeps_composed_identifier_safe(self) -> None:
            contract, run, units, events, digests = self.fixture()
            unit_id, test_id = "unit-Alpha1234567", "test-Beta8901234560"
            self.assertFalse(report.credential_bearing_text(unit_id))
            self.assertFalse(report.credential_bearing_text(test_id))
            self.assertEqual(len(unit_id + "/" + test_id), 37)
            units[0]["unit_id"] = unit_id
            units[0]["test_receipts"] = [{"test_id": test_id}]
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            digest = report.canonical_payload_digest(payload)
            data = report.render_report(payload, digest)
            self.assertTrue(report.validate_report_bytes(data, digest, payload))
            raw = data.replace(b"</main>", b"<p>Authorization: Basic body-credential-secret</p></main>")
            with self.assertRaisesRegex(ValueError, "credential-bearing"):
                report.validate_report_bytes(raw, digest, payload)
