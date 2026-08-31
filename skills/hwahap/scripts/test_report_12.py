try:
    from .test_reportkit import *
except ImportError:
    from test_reportkit import *

class ReportSlice28Tests(HwahapReportTests):
    def test_all_report_text_is_redacted_and_validator_rejects_raw_html(self) -> None:
            contract, run, units, events, digests = self.fixture()
            canary = "AWS_SECRET_ACCESS_KEY:=do-not-echo"
            self.assertEqual(report._text("secret handling"), "secret handling")
            contract["goals"] = [canary]
            run["deviations"] = [{"summary": canary, "root_cause": canary, "impact": canary,
                                  "prevention": canary, "evidence_explanation": canary,
                                  "evidence": [canary]}]
            run["deferred_security"] = [{"summary": canary, "reason": canary,
                                          "next_action": canary, "evidence": [canary]}]
            run["goal_link"]["current"] = {"mode": "unobserved", "reason": canary,
                                            "evidence": [canary]}
            run["metrics"]["token_usage"]["reason"] = canary
            run["final_review"]["attempts"][0]["evidence"] = [canary]
            units[0]["review_history"] = [{"round": 1, "diff_digest": "sha256:" + "a" * 64,
                                            "changed_paths": ["src"], "outcome": "fail",
                                            "verifier": {"evidence": [canary]},
                                            "scope_reviewer": {}}]
            units[0]["improvement_history"] = [{"after_round": 1, "kind": "terra_recovery",
                                                  "root_cause": canary, "hypothesis": canary,
                                                  "action": canary, "evidence": [canary]}]
            units[0]["failure"] = {"code": "HW_VERIFICATION_FAILED", "reason": canary,
                                     "evidence": [canary], "recovery": canary}
            events[0]["reason"] = canary
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            encoded = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("do-not-echo", encoded)
            digest = report.canonical_payload_digest(payload)
            data = report.render_report(payload, digest)
            self.assertNotIn("do-not-echo", data.decode())
            self.assertTrue(report.validate_report_bytes(data, digest, payload))
            raw = data.replace(b"</body>", b"AWS_SECRET_ACCESS_KEY=do-not-echo</body>")
            with self.assertRaisesRegex(ValueError, "credential-bearing"):
                report.validate_report_bytes(raw, digest, payload)

class ReportSlice29Tests(HwahapReportTests):
    def test_validator_rejects_raw_credentials_in_text_and_attributes(self) -> None:
            contract, run, units, events, digests = self.fixture()
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            digest = report.canonical_payload_digest(payload)
            data = report.render_report(payload, digest)
            raw_text = data.replace(b"</main>", b"<p>Authorization: Basic body-credential-secret</p></main>")
            with self.assertRaisesRegex(ValueError, "credential-bearing"):
                report.validate_report_bytes(raw_text, digest, payload)
            raw_attribute = data.replace(
                b'<main id="report">',
                b'<main id="report" data-leak="X-Api-Key: attr-credential-secret">',
            )
            with self.assertRaises(ValueError):
                report.validate_report_bytes(raw_attribute, digest, payload)

class ReportSlice30Tests(HwahapReportTests):
    def test_validator_rejects_credentials_in_structural_nodes(self) -> None:
            contract, run, units, events, digests = self.fixture()
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            digest = report.canonical_payload_digest(payload)
            data = report.render_report(payload, digest)
            credentials = (
                "Authorization: Basic comment-credential-secret",
                "Proxy-Authorization: Digest pi-credential-secret",
                "X-Api-Key: cdata-credential-secret",
                "x_api_key=Bearer declaration-credential-secret",
                "Cookie: cookie-credential-secret",
                "Password: password-credential-secret",
                "Private-Key: private-key-credential-secret",
            )
            wrappers = (
                lambda value: f"<!-- {value} -->",
                lambda value: f"<?{value}?>",
                lambda value: f"<![CDATA[{value}]]>",
                lambda value: f"<!{value}>",
            )
            for wrapper in wrappers:
                for credential in credentials:
                    with self.subTest(wrapper=wrapper, credential=credential):
                        injected = data.replace(b"</main>", (wrapper(credential) + "</main>").encode())
                        with self.assertRaises(ValueError):
                            report.validate_report_bytes(injected, digest, payload)
