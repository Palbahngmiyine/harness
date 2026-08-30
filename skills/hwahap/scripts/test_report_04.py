try:
    from .test_reportkit import *
except ImportError:
    from test_reportkit import *

class ReportSlice9Tests(HwahapReportTests):
    def test_state_scope_audit_integrates_through_render_and_cannot_change_gate(self) -> None:
            contract, run, units, events, digests = self.fixture()
            contract["allowed_paths"] = ["src", "src/*"]
            contract["forbidden_changes"] = []
            units[0]["unit_id"] = "unit-1"
            units[0]["allowed_paths"] = ["src", "src/*"]
            second = copy.deepcopy(units[0])
            second["unit_id"], second["allowed_paths"] = "unit-2", ["src/**"]
            units.append(second)
            snapshot = {"base_commit": "a" * 40, "target_commit": "b" * 40,
                        "base_tree": "c" * 40, "target_tree": "d" * 40,
                        "diff_digest": "sha256:" + "e" * 64,
                        "changed_paths": ["src/file.py", "src/file.py", "src/other.py"]}
            run["final_review"] = {"status": "pass", "attempts": [{
                "model": "gpt-5.6-sol", "effort": "ultra", "status": "pass",
                "thread_id": "final", "evidence": ["audit-evidence"],
                "diff_digest": snapshot["diff_digest"], "diff_snapshot": snapshot}]}
            audit = state.build_scope_audit(run, contract, units)
            self.assertEqual([item["path"] for item in audit["paths"]], ["src/file.py", "src/other.py"])
            self.assertEqual(audit["paths"][0]["matched_contract_rules"], ["src", "src/*"])
            self.assertEqual({item["unit_id"] for item in audit["paths"][0]["covering_passed_units"]}, {"unit-1", "unit-2"})
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests, audit)
            text = report.render_report(payload, report.canonical_payload_digest(payload)).decode()
            for marker in ("contract_allowed: True", "passed_unit_covered: True", "forbidden_overlap: False",
                           "src/*", "unit-2", snapshot["diff_digest"], contract["lock_sha256"]):
                self.assertIn(marker, text)
            self.assertTrue(report.validate_report_bytes(text.encode(), report.canonical_payload_digest(payload), payload))
            tampered = copy.deepcopy(audit)
            tampered["paths"][0]["verdict"] = "fail"
            errors: list[str] = []
            state.validate_final_review_snapshot_scope(run["final_review"], contract, units, errors)
            self.assertFalse(errors)
            self.assertEqual(report.build_payload("/tmp/work", contract, run, units, events, digests, tampered)["scope_audit"]["paths"][0]["verdict"], "fail")

class ReportSlice10Tests(HwahapReportTests):
    def test_all_allowlisted_evidence_fields_are_visible_in_static_html(self) -> None:
            contract, run, units, events, digests = self.fixture()
            events[0]["evidence_refs"] = ["event-evidence-sentinel"]
            units[0]["review_history"] = [{
                "round": 1, "changed_paths": ["src"], "outcome": "fail",
                "verifier": {"evidence": ["verifier-evidence-sentinel"]},
                "scope_reviewer": {"evidence": ["terra-evidence-sentinel"]},
            }]
            units[0]["failure"] = {"code": "HW_VERIFICATION_FAILED", "reason": "failure-reason-sentinel",
                                    "evidence": ["failure-evidence-sentinel"], "recovery": "failure-recovery-sentinel"}
            units[0]["recovery"] = {"reason": "recovery-reason-sentinel", "evidence": ["recovery-evidence-sentinel"],
                                     "action": "recovery-action-sentinel"}
            run["final_review"]["attempts"][0]["evidence"] = ["final-evidence-sentinel"]
            run["deviations"] = [{"summary": "deviation-summary-sentinel", "root_cause": "cause",
                                  "impact": "impact", "prevention": "prevention", "evidence": ["deviation-evidence-sentinel"]}]
            run["deferred_security"] = [{"summary": "deferred-summary-sentinel", "reason": "deferred-reason-sentinel",
                                          "next_action": "deferred-action", "evidence": ["deferred-evidence-sentinel"]}]
            run["goal_link"]["current"] = {"mode": "unobserved", "reason": "goal-reason-sentinel",
                                             "evidence": ["goal-evidence-sentinel"]}
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            text = report.render_report(payload, report.canonical_payload_digest(payload)).decode()
            for sentinel in (
                "event-evidence-sentinel", "verifier-evidence-sentinel", "terra-evidence-sentinel",
                "final-evidence-sentinel", "failure-evidence-sentinel", "recovery-evidence-sentinel",
                "deviation-evidence-sentinel", "deferred-reason-sentinel", "deferred-evidence-sentinel",
                "goal-reason-sentinel", "goal-evidence-sentinel",
            ):
                self.assertIn(sentinel, text)
            self.assertTrue(report.validate_report_bytes(text.encode(), report.canonical_payload_digest(payload), payload))
