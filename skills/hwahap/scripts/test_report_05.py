try:
    from .test_reportkit import *
except ImportError:
    from test_reportkit import *

class ReportSlice11Tests(HwahapReportTests):
    def test_curated_sections_show_required_metadata_and_history(self) -> None:
            contract, run, units, events, digests = self.fixture()
            contract.update({"goal_id": "curated-goal-id", "goal": "curated-goal", "lock_sha256": "curated-lock"})
            contract["spec"] = {"source": "curated-spec-source", "sha256": "curated-spec-sha", "confirmed_at": "curated-spec-time"}
            run["agent_profiles"] = {"curated-agent.toml": "sha256:" + "a" * 64}
            events[0].update({"type": "curated-type", "actor": "curated-actor", "role": "curated-role",
                              "input_digest": "curated-input", "review_round": 7})
            units[0]["acceptance_commands"] = ["curated acceptance command"]
            units[0]["review_history"] = [{"round": 2, "outcome": "curated-outcome", "changed_paths": ["curated-path"],
                "verifier": {"status": "curated-luna-status", "model": "curated-luna-model", "effort": "xhigh", "thread_id": "curated-luna-thread", "diff_digest": "curated-luna-diff", "evidence": ["curated-luna-evidence"]},
                "scope_reviewer": {"status": "curated-terra-status", "model": "curated-terra-model", "effort": "high", "thread_id": "curated-terra-thread", "diff_digest": "curated-terra-diff", "evidence": ["curated-terra-evidence"]}}]
            units[0]["recovery"] = {"reason": "curated-recovery-reason", "action": "curated-recovery-action", "evidence": ["curated-recovery-evidence"]}
            units[0]["improvement_history"] = [{"after_round": 3, "kind": "curated-kind", "failure_signature": "curated-signature",
                "root_cause": "curated-root", "hypothesis": "curated-hypothesis", "action": "curated-action",
                "strategy_digest": "curated-strategy", "scope_status": "curated-scope", "evidence": ["curated-improvement-evidence"]}]
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            text = report.render_report(payload, report.canonical_payload_digest(payload)).decode()
            def section(identifier: str) -> str:
                start = text.index(f'<section id="{identifier}">')
                end = text.find('<section id="', start + 1)
                return text[start:] if end < 0 else text[start:end]
            for marker in ("curated-goal-id", "curated-spec-source", "curated-spec-sha", "curated-spec-time"):
                self.assertIn(marker, section("contract"))
            for marker in ("curated-agent.toml", "sha256:" + "a" * 64):
                self.assertIn(marker, section("agents"))
            for marker in ("curated-type", "curated-actor", "curated-role", "curated-input"):
                self.assertIn(marker, section("timeline"))
            for marker in ("aggregate status", "curated-luna-model", "curated-luna-thread", "curated-luna-diff", "curated-terra-model", "curated-terra-thread", "curated-terra-diff", "curated-luna-evidence"):
                self.assertIn(marker, section("reviews"))
            for marker in ("curated-recovery-reason", "curated-recovery-action", "curated-improvement-evidence", "curated-signature", "curated-strategy", "curated-scope"):
                self.assertIn(marker, section("failures-recovery"))
            self.assertIn("acceptance-command-1", section("units"))
            self.assertTrue(report.validate_report_bytes(text.encode(), report.canonical_payload_digest(payload), payload))

class ReportSlice12Tests(HwahapReportTests):
    def test_unit_and_recovery_values_are_independently_visible(self) -> None:
            contract, run, units, events, digests = self.fixture()
            units[0].update({"writer": "writer-independent-sentinel", "replan_count": 4,
                             "failure": {"code": "HW_TEST_FAILED", "recovery": "failure-recovery-sentinel"},
                             "recovery": {"reason": "recovery-reason-independent-sentinel", "action": "recovery-action-independent-sentinel"}})
            payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
            text = report.render_report(payload, report.canonical_payload_digest(payload)).decode()
            units_section = text[text.index('<section id="units">'):text.index('<section id="timeline">')]
            failures_section = text[text.index('<section id="failures-recovery">'):text.index('<section id="provenance">')]
            for marker, section in (("writer-independent-sentinel", units_section), ("4", units_section),
                                    ("failure-recovery-sentinel", failures_section),
                                    ("recovery-reason-independent-sentinel", failures_section),
                                    ("recovery-action-independent-sentinel", failures_section)):
                self.assertIn(marker, section)
                self.assertGreaterEqual(text.count(marker), 2)
            self.assertTrue(report.validate_report_bytes(text.encode(), report.canonical_payload_digest(payload), payload))
