try:
    from .test_reportkit import *
except ImportError:
    from test_reportkit import *

class ReportSlice26Tests(HwahapReportTests):
    def test_report_data_checks_sensitive_dict_key_value_pairs_and_obfuscators(self) -> None:
            safe = {"Authorization": "Bearer [redacted]", "Proxy-Authorization": "Digest [redacted]",
                    "token_total": 3, "note": "token usage unavailable"}
            safe_bytes = report.canonical_payload_bytes(safe)
            self.assertTrue(report.validate_report_data_bytes(safe_bytes, safe, report.canonical_payload_digest(safe)))
            cases = (
                {"client-secret": "matrix-canary"}, {"github-token": "matrix-canary"},
                {"service-password": "matrix-canary"}, {"x-api-key": "matrix-canary"},
                {"x_api_key": "matrix-canary"}, {"Authorization": "Basic matrix-canary"},
                {"Proxy-Authorization": "Digest response=matrix-canary"},
                {"client\u200b-secret": "matrix-canary"}, {"github\u2028-token": "matrix-canary"},
                {"service\u2029password": "matrix-canary"}, {"x\u00a0api\u200bkey": "matrix-canary"},
                {"nested": [{"password": "matrix-canary"}]}, {"client-secret": ["matrix-canary"]},
            )
            for unsafe in cases:
                with self.subTest(unsafe=unsafe):
                    data = report.canonical_payload_bytes(unsafe)
                    with self.assertRaisesRegex(report.HwahapReportError, "report data is invalid") as raised:
                        report.validate_report_data_bytes(data, unsafe, report.canonical_payload_digest(unsafe))
                    self.assertNotIn("matrix-canary", str(raised.exception))

class ReportSlice27Tests(HwahapReportTests):
    def test_acceptance_commands_are_digest_only(self) -> None:
            contract, run, units, events, digests = self.fixture()
            authentication_url = "https://" + "user" + ":" + "pass" + "@example.invalid"
            canary = "AWS_SESSION_TOKEN=" + "report-canary curl " + authentication_url
            contract["test_commands"] = [canary]
            units[0]["acceptance_commands"] = [canary]
            units[0]["test_receipts"] = [{"test_id": "test-1-1", "command_index": 1,
                                           "command_sha256": "sha256:" + "a" * 64,
                                           "source": "codex.exec_command", "execution_receipt_sha256": "sha256:" + "c" * 64,
                                           "observer_role": "verifier", "observer_thread_id": "luna-receipt",
                                           "diff_digest": "sha256:" + "d" * 64,
                                           "started_at": "start", "ended_at": "end", "exit_code": 0,
                                           "output_sha256": "sha256:" + "b" * 64, "status": "pass"}]
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            encoded = json.dumps(payload, ensure_ascii=False)
            digest = report.canonical_payload_digest(payload)
            data = report.render_report(payload, digest).decode()
            self.assertNotIn(canary, encoded)
            self.assertNotIn(canary, data)
            self.assertEqual(payload["units"][0]["acceptance_commands"][0]["name"], "acceptance-command-1")
            self.assertRegex(payload["units"][0]["acceptance_commands"][0]["sha256"], r"^sha256:[0-9a-f]{64}$")
            self.assertIn("test-1-1", encoded)
            self.assertIn("test-1-1", data)
            for value in ("codex.exec_command", "verifier", "luna-receipt", "sha256:" + "c" * 64, "sha256:" + "d" * 64,
                          "sha256:" + "a" * 64, "sha256:" + "b" * 64, "start", "end", "exit code"):
                self.assertIn(value, data)
            self.assertIn("기록된 테스트 실행 수", data)
            self.assertIn("overflow-wrap:anywhere", data)
            self.assertIn("receipt-list", data)
            self.assertNotIn("subprocess-stdout-canary", data)
