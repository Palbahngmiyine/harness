"""Focused tests for the static Hwahap report generator."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("hwahap_report.py")
SPEC = importlib.util.spec_from_file_location("hwahap_report", MODULE_PATH)
assert SPEC and SPEC.loader
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)
STATE_SPEC = importlib.util.spec_from_file_location("hwahap_state_for_report", MODULE_PATH.with_name("hwahap_state.py"))
assert STATE_SPEC and STATE_SPEC.loader
state = importlib.util.module_from_spec(STATE_SPEC)
STATE_SPEC.loader.exec_module(state)


def _relative_luminance(value: str) -> float:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(character * 2 for character in value)
    channels = [int(value[index:index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
              for channel in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    lighter, darker = sorted((_relative_luminance(first), _relative_luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


class _ReviewTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[tuple[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self.rows.append([])
        elif tag in {"th", "td"} and self.rows:
            self.rows[-1].append((tag, dict(attrs).get("colspan")))


class HwahapReportTests(unittest.TestCase):
    def fixture(self) -> tuple[dict, dict, list[dict], list[dict], dict]:
        contract = {field: ["src"] for field in report.CONTRACT_LISTS}
        contract.update({"schema_version": 1, "goal_id": "g", "goal": "<script>alert(1)</script>", "locked": True,
                         "lock_sha256": "sha256:" + "a" * 64,
                         "spec": {"source": "/tmp/work/spec.md", "sha256": "b" * 64, "confirmed_at": "now"},
                         "unknown": "do not include"})
        run = {"schema_version": 1, "goal_id": "g", "status": "completed", "started_at": "now",
               "completed_at": "later", "roles": {"orchestrator": {"agent": "sol", "model": "gpt-5.6-sol", "effort": "xhigh", "fast": "Fast"}},
               "agent_profiles": {"sol.toml": "sha256:" + "c" * 64}, "fast_status": "unknown",
               "metrics": {"unit_count": 1, "agent_runs": {"availability": "unavailable", "reason": "platform aggregate not exposed", "source": None, "total": None}, "review_rounds": 1, "test_runs": 1, "token_usage": {"availability": "unavailable", "reason": "hidden", "total": None}},
               "deviations": [], "deferred_security": [], "final_review": {"status": "pass", "attempts": [{"model": "gpt-5.6-sol", "effort": "ultra", "status": "pass", "thread_id": "final", "evidence": ["review"]}]},
               "goal_link": {"current": {"mode": "unobserved"}, "history": []}, "raw_log": "secret"}
        unit = {"unit_id": "u", "title": "unit", "status": "passed", "allowed_paths": ["/tmp/work/src"],
                "acceptance_commands": ["pytest"], "review_history": [], "improvement_history": [],
                "failure": {}, "recovery": {}, "prompt": "ignore this"}
        event = {field: (1 if field == "sequence" else 0 if field == "review_round" else ["ev"] if field == "evidence_refs" else "value") for field in report.EVENT_FIELDS}
        return contract, run, [unit], [event], {"contract": "sha256:" + "d" * 64}

    def test_static_report_has_required_sections_and_material3_contract(self) -> None:
        contract, run, units, events, digests = self.fixture()
        payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
        digest = report.canonical_payload_digest(payload)
        data = report.render_report(payload, digest)
        self.assertTrue(report.validate_report_bytes(data, digest, payload))
        text = data.decode()
        self.assertIn('<h1>Hwahap 실행 결과</h1>', text)
        self.assertIn('<meta name="material-design-system" content="Material Design 3 theme">', text)
        self.assertIn('<meta name="material-theme-source" content="OpenDesign material fixture">', text)
        self.assertIn('a554d017c8fa12d8913354ba6cf792d26d0c3b54', text)
        self.assertIn('--bg:#f8fafd', text)
        self.assertIn('--surface:#fff', text)
        self.assertIn('--accent:#1a73e8', text)
        self.assertIn('--md-sys-color-primary', text)
        self.assertIn('--md-sys-typescale-display-large', text)
        self.assertIn('--md-sys-shape-corner-large', text)
        self.assertIn('--md-sys-elevation-level1', text)
        self.assertIn('--md-sys-motion-standard-effects', text)
        self.assertIn('prefers-color-scheme:dark', text)
        self.assertIn('prefers-contrast:more', text)
        self.assertIn('prefers-reduced-motion:reduce', text)
        self.assertNotIn('Astryx', text)
        self.assertNotIn('<script', text)
        self.assertNotIn('<link', text)
        self.assertIn('id="agents"', text)
        self.assertIn('gpt-5.6-sol', text)
        self.assertIn('final', text)
        self.assertIn('Acceptance commands', text)
        self.assertIn('확인 가능 여부', text)
        self.assertIn('viewport', text)
        self.assertIn('platform aggregate not exposed', text)
        self.assertIn('총 토큰', text)
        self.assertIn('확인할 수 없음', text)
        self.assertIn('기록 없음', text)
        self.assertNotIn('>None<', text)
        self.assertNotIn("{'availability':", text)
        for label in ('목표', '제외 범위', '허용 경로', '금지 변경', '완료 기준', '테스트 명령', '작업 단위', '에이전트 실행', '검수 회차', '확인 가능 여부', '사유'):
            self.assertIn(label, text)
        self.assertIn('class="table-wrap"', text)
        self.assertNotIn('<pre>', text)
        for semantic in ('summary-grid', '<nav class="section-nav"', '<details id="evidence-vault"',
                         'class="outcome-panel panel"',
                         '<ol class="timeline">', '<caption>', '<table>', '<dl>'):
            self.assertIn(semantic, text)

    def test_report_css_wraps_long_tokens_and_preserves_table_scroll_contract(self) -> None:
        contract, run, units, events, digests = self.fixture()
        payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
        digest = report.canonical_payload_digest(payload)
        text = report.render_report(payload, digest).decode()
        self.assertIn("background:radial-gradient(circle at 88% 8%", text)
        self.assertIn("color:var(--fg);font:var(--md-sys-typescale-body-large)", text)
        self.assertIn(".table-wrap{max-width:100%;overflow-x:auto", text)
        self.assertIn("table{border-collapse:collapse;width:100%;min-width:700px;background:var(--surface)", text)
        self.assertIn("td,th{padding:var(--space-3);text-align:start;vertical-align:top;overflow-wrap:anywhere", text)
        self.assertIn("@media (max-width:639px)", text)
        self.assertIn("@media (min-width:640px) and (max-width:1023px)", text)
        self.assertIn("@media (min-width:1024px)", text)
        self.assertTrue(report.validate_report_bytes(text.encode(), digest, payload))

    def test_opendesign_material_tokens_cover_foundations_and_accessible_color_pairs(self) -> None:
        style = report.STYLE_BLOCK
        fixture_tokens = (
            "--bg:#f8fafd", "--surface:#fff", "--surface-warm:#e8f0fe", "--fg:#202124",
            "--fg-2:#3c4043", "--muted:#5f6368", "--meta:#1a73e8", "--border:#dadce0",
            "--border-soft:#edf0f2", "--accent:#1a73e8", "--accent-on:#fff",
            "--success:#188038", "--warn:#f9ab00", "--danger:#d93025",
            "--font-display:", "--font-body:", "--font-mono:", "--text-xs:12px",
            "--text-4xl:64px", "--space-1:4px", "--space-12:48px", "--radius-sm:4px",
            "--radius-md:12px", "--radius-lg:24px", "--radius-pill:9999px",
            "--elev-ring:", "--elev-raised:", "--focus-ring:", "--motion-fast:150ms",
            "--motion-base:250ms", "--container-max:1200px",
        )
        for token in fixture_tokens:
            self.assertIn(token, style)
        for role in ("display", "headline", "title", "body", "label"):
            for size in ("large", "medium", "small"):
                self.assertIn(f"--md-sys-typescale-{role}-{size}:", style)
        for shape in ("extra-small", "medium", "large", "full"):
            self.assertIn(f"--md-sys-shape-corner-{shape}:", style)
        for foundation in ("--md-sys-color-primary", "--md-sys-elevation-level1",
                           "--md-sys-motion-standard-effects"):
            self.assertIn(foundation, style)
        light_pairs = (
            ("#202124", "#f8fafd"), ("#202124", "#ffffff"), ("#5f6368", "#ffffff"),
            ("#ffffff", "#1a73e8"), ("#0d652d", "#e6f4ea"),
            ("#5f4500", "#fef7e0"), ("#a50e0e", "#fce8e6"),
        )
        dark_pairs = (
            ("#f8fafc", "#0f1115"), ("#a7adba", "#171a21"),
            ("#8ab4f8", "#171a21"), ("#062e6f", "#8ab4f8"),
            ("#b7f5c8", "#173b24"), ("#fff1b8", "#453600"),
            ("#ffd7d3", "#4a1d1a"),
        )
        for foreground, background in (*light_pairs, *dark_pairs):
            with self.subTest(foreground=foreground, background=background):
                self.assertGreaterEqual(_contrast(foreground, background), 4.5)

    def test_human_summary_precedes_collapsed_complete_evidence(self) -> None:
        contract, run, units, events, digests = self.fixture()
        run["deviations"] = [{"summary": "문제", "root_cause": "원인", "impact": "이전 영향",
                              "prevention": "적용한 개선", "evidence": ["검증 근거"]}]
        run["deferred_security"] = [{"summary": "남은 위험", "reason": "미검증",
                                     "next_action": "사용자 결정", "evidence": ["경계"]}]
        run["improvement_candidates"] = [{"status": "proposed", "summary": "후속 후보",
                                           "evidence": ["검토"], "expected_effect": "기대 효과",
                                           "next_action": "다음 결정"}]
        payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
        digest = report.canonical_payload_digest(payload)
        text = report.render_report(payload, digest).decode()
        ordered = ("summary", "deviations", "improvement-candidates", "next-actions", "tests-metrics",
                   "evidence-vault", "contract", "agents", "units", "timeline", "reviews", "scope-audit",
                   "failures-recovery", "provenance", "report-data")
        positions = [text.index(f'id="{identifier}"') for identifier in ordered]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn('id="evidence-vault" class="evidence-vault" open', text)
        self.assertIn('class="change-card panel"', text)
        self.assertIn('class="risk-card tile"', text)
        self.assertIn('class="proposal-card tile"', text)
        for phrase in ("이전 문제", "발생 원인", "적용한 개선", "이전 대비 기대 변화",
                       "아직 남은 위험", "기대 효과", "다음 결정", "실제 운영 효과를 보장"):
            self.assertIn(phrase, text)
        self.assertIn("이전 문제”가 다시 발생하기 전에 “적용한 개선", text)
        self.assertIn("min-block-size:48px", text)
        self.assertIn("box-shadow:var(--focus-ring)", text)
        self.assertIn('<caption>정본 report-data.json ledger', text)
        self.assertTrue(report.validate_report_bytes(text.encode(), digest, payload))

    def test_provenance_values_are_visible_in_payload_and_html(self) -> None:
        contract, run, units, events, digests = self.fixture()
        spec = {"source": "spec-source-sentinel", "sha256": "spec-sha-sentinel", "confirmed_at": "spec-confirmed-sentinel"}
        contract["spec"] = spec
        final_digests = ("sha256:" + "1" * 64, "sha256:" + "2" * 64)
        run.update({
            "fast_status": "fast-status-sentinel",
            "final_review": {"status": "pass", "attempts": [
                {"model": "sol", "effort": "ultra", "status": "pass", "thread_id": "attempt-one", "diff_digest": final_digests[0]},
                {"model": "sol", "effort": "xhigh", "status": "unavailable", "thread_id": "attempt-two", "diff_digest": final_digests[1]},
            ]},
            "goal_link": {"current": {
                "thread_id": "goal-thread-sentinel", "receipt_sha256": "goal-receipt-sentinel",
                "objective_sha256": "goal-objective-sentinel", "observed_at": "goal-observed-sentinel",
                "token_total": 987654, "source": "goal-source-sentinel", "mode": "goal-mode-sentinel",
                "completion_sync": "goal-sync-sentinel", "sync_result": "goal-result-sentinel",
                "reason": "Authorization: Bearer provenance-secret",
            }, "history": []},
        })
        digests = {"contract-sentinel": "sha256:" + "3" * 64, "events-sentinel": "sha256:" + "4" * 64}
        run["agent_profiles"] = {"sol-sentinel.toml": "sha256:" + "5" * 64, "luna-sentinel.toml": "sha256:" + "6" * 64}
        payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
        encoded = json.dumps(payload, ensure_ascii=False)
        text = report.render_report(payload, report.canonical_payload_digest(payload)).decode()
        sentinels = (
            "fast-status-sentinel", *final_digests, "goal-thread-sentinel", "goal-receipt-sentinel",
            "goal-objective-sentinel", "goal-observed-sentinel", "987654", "goal-source-sentinel",
            "goal-mode-sentinel", "goal-sync-sentinel", "goal-result-sentinel", "spec-source-sentinel",
            "spec-sha-sentinel", "spec-confirmed-sentinel", "contract-sentinel", "events-sentinel",
            "sha256:" + "3" * 64, "sha256:" + "4" * 64, "sol-sentinel.toml", "luna-sentinel.toml",
            "sha256:" + "5" * 64, "sha256:" + "6" * 64,
        )
        for value in sentinels:
            self.assertIn(value, encoded)
            self.assertIn(value, text)
        self.assertNotIn("provenance-secret", encoded)
        self.assertNotIn("provenance-secret", text)
        self.assertIn("Authorization: Bearer [redacted]", encoded)
        self.assertTrue(report.validate_report_bytes(text.encode(), report.canonical_payload_digest(payload), payload))

    def test_diff_snapshots_are_allowlisted_and_visible(self) -> None:
        contract, run, units, events, digests = self.fixture()
        snapshot = {"base_commit": "a" * 40, "target_commit": "b" * 40,
                    "base_tree": "c" * 40, "target_tree": "d" * 40,
                    "diff_digest": "sha256:" + "e" * 64, "changed_paths": ["snapshot-path"]}
        review = {"round": 1, "diff_snapshot": {**snapshot, "hostile": "drop-review"},
                  "verifier": {}, "scope_reviewer": {}}
        units[0]["review_history"] = [review]
        units[0]["test_receipts"] = [{"test_id": "receipt", "diff_snapshot": {**snapshot, "hostile": "drop-receipt"}}]
        run["final_review"]["attempts"][0]["diff_snapshot"] = {**snapshot, "hostile": "drop-final"}
        payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
        self.assertEqual(payload["reviews"]["units"][0]["history"][0]["diff_snapshot"], snapshot)
        self.assertEqual(payload["tests-metrics"]["test_receipts"][0]["receipts"][0]["diff_snapshot"], snapshot)
        self.assertEqual(payload["reviews"]["final_review"]["attempts"][0]["diff_snapshot"], snapshot)
        encoded = json.dumps(payload, ensure_ascii=False)
        text = report.render_report(payload, report.canonical_payload_digest(payload)).decode()
        for value in snapshot.values():
            for marker in value if isinstance(value, list) else (value,):
                self.assertIn(marker, encoded)
                self.assertIn(marker, text)
        self.assertNotIn("drop-review", encoded + text)
        self.assertNotIn("drop-receipt", encoded + text)
        self.assertNotIn("drop-final", encoded + text)
        self.assertTrue(report.validate_report_bytes(text.encode(), report.canonical_payload_digest(payload), payload))

    def test_review_table_snapshot_column_matches_header(self) -> None:
        contract, run, units, events, digests = self.fixture()
        units[0]["review_history"] = [{"round": 1, "outcome": "pass", "verifier": {}, "scope_reviewer": {}}]
        payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
        text = report.render_report(payload, report.canonical_payload_digest(payload)).decode()
        parser = _ReviewTableParser()
        parser.feed(text[text.index('<section id="reviews">'):text.index('<section id="scope-audit">')])
        self.assertEqual(len(parser.rows[0]), 9)
        self.assertTrue(all(len(row) == len(parser.rows[0]) for row in parser.rows[1:]))
        empty_payload = report.build_payload("/tmp/work", contract, run, self.fixture()[2], events, digests)
        empty = report.render_report(empty_payload, report.canonical_payload_digest(empty_payload)).decode()
        empty_parser = _ReviewTableParser()
        empty_parser.feed(empty[empty.index('<section id="reviews">'):empty.index('<section id="scope-audit">')])
        self.assertEqual(empty_parser.rows[1][0][1], "9")

    def test_scope_audit_is_allowlisted_and_visible(self) -> None:
        contract, run, units, events, digests = self.fixture()
        audit = {"authority": "attacker-value", "affects_gate": True,
                 "source_diff_digest": "sha256:" + "a" * 64,
                 "contract_lock_sha256": "sha256:" + "b" * 64, "hostile": "omit", "paths": [{
                     "path": "src", "contract_allowed": True, "passed_unit_covered": True,
                     "forbidden_overlap": False, "matched_contract_rules": ["src"],
                     "covering_passed_units": [{"unit_id": "u", "matched_rules": ["src"]}],
                     "matched_forbidden_rules": [], "verdict": "pass",
                     "evidence": {"diff_digest": "sha256:" + "a" * 64,
                                  "contract_lock_sha256": "sha256:" + "b" * 64,
                                  "passed_unit_ids": ["u"], "hostile": "omit"},
                     "hostile": "omit"}]}
        payload = report.build_payload("/tmp/work", contract, run, units, events, digests, audit)
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["scope_audit"]["authority"], "derived-report-only")
        self.assertNotIn("hostile", json.dumps(payload, ensure_ascii=False))
        text = report.render_report(payload, report.canonical_payload_digest(payload)).decode()
        self.assertIn('id="scope-audit"', text)
        self.assertIn("src", text)
        self.assertTrue(report.validate_report_bytes(text.encode(), report.canonical_payload_digest(payload), payload))

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

    def test_authorization_header_variants_are_redacted_across_evidence_sections(self) -> None:
        contract, run, units, events, digests = self.fixture()
        variants = (
            "Authorization: Basic report-basic-secret",
            "Authorization: Digest report-digest-secret",
            'Authorization: Digest username="report-user", realm="report-realm", response="report-response"',
            "Authorization: Basic report-lf-secret\nnext-line",
            "Proxy-Authorization: Basic report-crlf-secret\r\nnext-line",
            'Authorization: Digest username="report-fold-user"\r\n  realm="report-fold-realm"\r\n\tresponse="report-fold-response"',
            "Authorization: Basic [redacted]\r\n\tusername=report-basic-redacted-fold-secret",
            "Authorization: Digest [redacted]\n  username=report-digest-redacted-fold-secret",
            "Proxy-Authorization: Basic [redacted]\r\n\tproxy=report-proxy-redacted-fold-secret",
            "Proxy-Authorization: Bearer report-proxy-bearer-secret",
            "Proxy-Authorization: Basic report-proxy-basic-secret",
            "Proxy-Authorization: Digest report-proxy-digest-secret",
            "X-Api-Key: report-api-key-secret",
            "Authorization: Basic [redacted] report-redacted-tail-secret",
            "Authorization: Digest [redacted] report-digest-redacted-tail-secret",
            "Proxy-Authorization: Digest [redacted] report-proxy-redacted-tail-secret",
            "Authorization: Basic report-prefix-secret [redacted]",
            "Authorization: Digest report-digest-prefix-secret [redacted]",
            "Proxy-Authorization: Digest report-proxy-prefix-secret [redacted]",
            "Authorization: Basic report-basic-cr-secret\rnext-line",
            "Authorization: Digest report-digest-cr-secret\r\tresponse=report-digest-cr-folded",
            "Authorization: Bearer report-bearer-cr-secret\rnext-line",
            "Proxy-Authorization: Basic report-proxy-basic-cr-secret\rnext-line",
            "Proxy-Authorization: Digest report-proxy-digest-cr-secret\r\tresponse=report-proxy-digest-cr-folded",
            "Proxy-Authorization: Bearer report-proxy-bearer-cr-secret\rnext-line",
            "Authorization: Basic [redacted]\rresponse=report-basic-redacted-cr-sentinel",
            "Authorization: Digest [redacted]\rresponse=report-digest-redacted-cr-sentinel",
            "Authorization: Bearer [redacted]\rresponse=report-bearer-redacted-cr-sentinel",
            "Proxy-Authorization: Basic [redacted]\rresponse=report-proxy-basic-redacted-cr-sentinel",
            "Proxy-Authorization: Digest [redacted]\rresponse=report-proxy-digest-redacted-cr-sentinel",
            "Proxy-Authorization: Bearer [redacted]\rresponse=report-proxy-bearer-redacted-cr-sentinel",
        )
        run["deferred_security"] = [{"summary": "deferred", "reason": variants[0], "next_action": "wait", "evidence": [variants[1], variants[2], variants[3], variants[6]]}]
        run["goal_link"]["current"] = {"mode": "unobserved", "reason": variants[4], "evidence": [variants[5], variants[7], variants[9]]}
        units[0]["review_history"] = [{"round": 1, "outcome": "fail", "verifier": {},
                                        "scope_reviewer": {"evidence": [variants[8], variants[10], variants[11], variants[12], variants[13], variants[14], variants[15], variants[16], variants[17], variants[18], variants[19], variants[20], variants[21], variants[22], variants[23], variants[24], variants[25], variants[26], variants[27], variants[28], variants[29], variants[30]]}}]
        payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
        encoded = json.dumps(payload, ensure_ascii=False)
        digest = report.canonical_payload_digest(payload)
        text = report.render_report(payload, digest).decode()
        raw_tokens = (
            "report-basic-secret", "report-digest-secret", "report-user", "report-realm", "report-response",
            "report-lf-secret", "report-crlf-secret", "report-fold-user", "report-fold-realm", "report-fold-response",
            "report-basic-redacted-fold-secret", "report-digest-redacted-fold-secret", "report-proxy-redacted-fold-secret",
            "report-proxy-bearer-secret", "report-proxy-basic-secret", "report-proxy-digest-secret", "report-api-key-secret",
            "report-redacted-tail-secret", "report-digest-redacted-tail-secret", "report-proxy-redacted-tail-secret",
            "report-prefix-secret", "report-digest-prefix-secret", "report-proxy-prefix-secret",
            "report-basic-cr-secret", "report-digest-cr-secret", "report-bearer-cr-secret",
            "report-proxy-basic-cr-secret", "report-proxy-digest-cr-secret", "report-proxy-bearer-cr-secret",
            "report-digest-cr-folded", "report-proxy-digest-cr-folded",
            "report-basic-redacted-cr-sentinel", "report-digest-redacted-cr-sentinel", "report-bearer-redacted-cr-sentinel",
            "report-proxy-basic-redacted-cr-sentinel", "report-proxy-digest-redacted-cr-sentinel", "report-proxy-bearer-redacted-cr-sentinel",
        )
        for value in raw_tokens:
            self.assertNotIn(value, encoded)
            self.assertNotIn(value, text)
        for marker in ("Authorization: Basic [redacted]", "Authorization: Digest [redacted]",
                       "Proxy-Authorization: Bearer [redacted]", "Proxy-Authorization: Basic [redacted]",
                       "Proxy-Authorization: Digest [redacted]", "X-Api-Key: [redacted]"):
            self.assertIn(marker, encoded)
            self.assertIn(marker, text)
        self.assertIn("next-line", encoded)
        self.assertIn("next-line", text)
        for safe in ("Authorization: Basic [redacted]", "Authorization: Digest [redacted]",
                     "Proxy-Authorization: Basic [redacted]", "Proxy-Authorization: Digest [redacted]",
                     "Authorization: Bearer [redacted]", "Proxy-Authorization: Bearer [redacted]"):
            self.assertFalse(report.contains_sensitive_data(safe))
            self.assertEqual(report._text(safe), safe)
        self.assertTrue(report.validate_report_bytes(text.encode(), digest, payload))

    def test_other_header_variants_are_redacted_across_payload_and_html(self) -> None:
        contract, run, units, events, digests = self.fixture()
        variants = (
            "X-Api-Key: [redacted]\rresponse=report-api-fold-secret",
            "X-Api-Key: report-api-prefix-secret [redacted]",
            "Cookie: [redacted]\r\n\treport-cookie-fold-secret",
            "Cookie: report-cookie-prefix-secret [redacted]",
            "Password: [redacted]\rreport-password-fold-secret",
            "Password: report-password-prefix-secret [redacted]",
            "x_api_key=Basic report-x-under-basic-secret",
            "x-api-key=Digest report-x-hyphen-digest-secret",
            "x api key: Bearer report-x-spaced-bearer-secret",
            "x_api_key=Basic [redacted]\nSECRET_KEY=report-overlap-secret",
            "Authorization: Basic <report-auth-angle-prefix>",
            "Proxy-Authorization: Digest report-proxy-angle-prefix<report-proxy-angle-suffix>",
            "X-Api-Key: <report-x-angle-prefix>",
            "x_api_key=Basic report-x-under-angle-prefix<report-x-under-angle-suffix>",
            "Cookie: <report-cookie-angle-prefix>",
            "Password: report-password-angle-prefix<report-password-angle-suffix>",
            "Private-Key: <report-private-angle-prefix>",
        )
        safe_variants = ("x_api_key=Basic [redacted]", "X_API_KEY=Digest [redacted]", "x api key: Bearer [redacted]")
        run["deferred_security"] = [{"summary": "deferred", "reason": variants[0], "next_action": "wait", "evidence": list(variants[1:]) + list(safe_variants)}]
        payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
        encoded = json.dumps(payload, ensure_ascii=False)
        digest = report.canonical_payload_digest(payload)
        text = report.render_report(payload, digest).decode()
        for value in ("report-api-fold-secret", "report-api-prefix-secret", "report-cookie-fold-secret",
            "report-cookie-prefix-secret", "report-password-fold-secret", "report-password-prefix-secret",
            "report-x-under-basic-secret", "report-x-hyphen-digest-secret", "report-x-spaced-bearer-secret",
            "report-auth-angle-prefix", "report-proxy-angle-prefix", "report-proxy-angle-suffix",
            "report-x-angle-prefix", "report-x-under-angle-prefix", "report-x-under-angle-suffix",
            "report-cookie-angle-prefix", "report-password-angle-prefix", "report-password-angle-suffix",
            "report-private-angle-prefix"):
            self.assertNotIn(value, encoded)
            self.assertNotIn(value, text)
        self.assertNotIn("report-overlap-secret", encoded)
        self.assertNotIn("report-overlap-secret", text)
        for value in variants:
            cleaned = report._text(value)
            self.assertEqual(report._text(cleaned), cleaned)
            self.assertNotIn("[redacted] [redacted]", cleaned)
            self.assertNotIn("[redacted] [redacted]", encoded)
            self.assertNotIn("[redacted] [redacted]", text)
        for marker in ("X-Api-Key: [redacted]", "Cookie: [redacted]", "Password: [redacted]",
                       "Authorization: Basic [redacted]", "Proxy-Authorization: Digest [redacted]",
                       "Private-Key: [redacted]"):
            self.assertIn(marker, encoded)
            self.assertIn(marker, text)
        for safe in ("X-Api-Key: [redacted]", "Cookie: [redacted]", "Password: [redacted]"):
            self.assertFalse(report.contains_sensitive_data(safe))
            self.assertEqual(report._text(safe), safe)
        for safe in safe_variants:
            self.assertFalse(report.contains_sensitive_data(safe))
            self.assertEqual(report._text(report._text(safe)), report._text(safe))
        self.assertTrue(report.validate_report_bytes(text.encode(), digest, payload))

    def test_empty_sections_are_readable(self) -> None:
        contract, run, _, events, digests = self.fixture()
        payload = report.build_payload('/tmp/work', contract, run, [], events, digests)
        text = report.render_report(payload, report.canonical_payload_digest(payload)).decode()
        self.assertGreaterEqual(text.count('기록 없음'), 4)
        self.assertIn('id="units"', text)
        self.assertIn('id="reviews"', text)
        self.assertIn('id="failures-recovery"', text)
        self.assertIn('id="deviations"', text)

    def test_completed_run_improvement_candidates_are_allowlisted_and_visible(self) -> None:
        contract, run, units, events, digests = self.fixture()
        run["improvement_candidates"] = [{
            "status": "proposed", "summary": "sentinel summary", "evidence": ["sentinel evidence", "Authorization: Bearer candidate-secret"],
            "expected_effect": "sentinel effect", "next_action": "sentinel next action",
            "command": "forbidden-command-sentinel", "path": "forbidden-path-sentinel", "unit_id": "forbidden-unit-sentinel",
        }]
        payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
        candidate = payload["improvement-candidates"][0]
        self.assertEqual(set(candidate), set(report.IMPROVEMENT_CANDIDATE_FIELDS))
        self.assertEqual(candidate["status"], "proposed")
        encoded = json.dumps(payload, ensure_ascii=False)
        digest = report.canonical_payload_digest(payload)
        data = report.render_report(payload, digest)
        text = data.decode()
        self.assertTrue(report.validate_report_bytes(data, digest, payload))
        for value in ("sentinel summary", "sentinel evidence", "sentinel effect", "sentinel next action"):
            self.assertIn(value, encoded)
            self.assertIn(value, text)
        for value in ("forbidden-command-sentinel", "forbidden-path-sentinel", "forbidden-unit-sentinel"):
            self.assertNotIn(value, encoded)
            self.assertNotIn(value, text)
        self.assertNotIn("candidate-secret", encoded)
        self.assertNotIn("candidate-secret", text)
        self.assertIn("Authorization: Bearer [redacted]", text)
        self.assertIn('id="improvement-candidates"', text)
        self.assertIn("보고 전용 · 사용자 승인 전에는 실행하지 않음", text)
        self.assertIn(digest, text)

    def test_report_preserves_long_text_and_complete_histories(self) -> None:
        contract, run, units, _, digests = self.fixture()
        long_text = "x" * 400 + "-end-sentinel"
        units[0]["test_receipts"] = [{"test_id": f"receipt-{index}"} for index in range(1, 101)] + [{"test_id": "receipt-101-sentinel"}]
        units[0]["review_history"] = [{"round": index, "changed_paths": [f"review-{index}"]} for index in range(1, 101)] + [{"round": 101, "changed_paths": ["review-101-sentinel"]}]
        units[0]["improvement_history"] = [{"after_round": index, "action": f"improvement-{index}"} for index in range(1, 101)] + [{"after_round": 101, "action": "improvement-101-sentinel"}]
        run["goal_link"]["history"] = [{"reason": f"goal-history-{index}"} for index in range(1, 101)] + [{"reason": "goal-history-101-sentinel"}]
        run["improvement_candidates"] = [{"summary": f"candidate-{index}"} for index in range(1, 101)] + [{"summary": "candidate-101-sentinel"}]
        run["deviations"] = [{"summary": f"deviation-{index}"} for index in range(1, 101)] + [{"summary": long_text}]
        run["deferred_security"] = [{"summary": f"deferred-{index}"} for index in range(1, 101)] + [{"summary": "deferred-101-sentinel"}]
        run["final_review"]["attempts"] = [{"thread_id": f"attempt-{index}"} for index in range(1, 21)] + [{"thread_id": "attempt-21-sentinel"}]
        events = [{"sequence": index, "entity": "event", "from": "before", "to": "after", "reason": f"event-{index}"} for index in range(1, 501)] + [{"sequence": 501, "entity": "event", "from": "before", "to": "after", "reason": "event-501-sentinel"}]

        payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
        digest = report.canonical_payload_digest(payload)
        text = report.render_report(payload, digest).decode()
        parsed = json.loads(report.canonical_payload_bytes(payload))

        self.assertEqual(len(parsed["deviations"]["items"]), 101)
        self.assertEqual(payload["deviations"]["items"][-1]["summary"], long_text)
        self.assertEqual(len(payload["deviations"]["items"][-1]["summary"]), len(long_text))
        self.assertEqual(len(payload["units"][0]["test_receipts"]), 101)
        self.assertEqual(len(payload["units"][0]["review_history"]), 101)
        self.assertEqual(len(payload["units"][0]["improvement_history"]), 101)
        self.assertEqual(len(payload["provenance"]["goal_link"]["history"]), 101)
        self.assertEqual(len(payload["improvement-candidates"]), 101)
        self.assertEqual(len(payload["deviations"]["deferred_security"]), 101)
        self.assertEqual(len(payload["reviews"]["final_review"]["attempts"]), 21)
        self.assertEqual(len(parsed["timeline"]), 501)
        for sentinel in ("receipt-101-sentinel", "review-101-sentinel", "improvement-101-sentinel",
                         "goal-history-101-sentinel", "candidate-101-sentinel", long_text,
                         "deferred-101-sentinel", "attempt-21-sentinel", "event-501-sentinel"):
            self.assertIn(sentinel, json.dumps(parsed, ensure_ascii=False))
            self.assertIn(sentinel, text)
        self.assertTrue(report.validate_report_bytes(text.encode(), digest, payload))

    def test_validator_requires_improvement_candidates_section(self) -> None:
        contract, run, units, events, digests = self.fixture()
        payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
        digest = report.canonical_payload_digest(payload)
        data = report.render_report(payload, digest).replace(b'id="improvement-candidates"', b'id="missing-improvement-candidates"')
        with self.assertRaisesRegex(ValueError, "missing report section: improvement-candidates"):
            report.validate_report_bytes(data, digest, payload)

    def test_escape_redact_paths_and_exclude_unknown_values(self) -> None:
        contract, run, units, events, digests = self.fixture()
        authentication_url = "https://" + "user" + ":" + "pass" + "@example.invalid/x"
        private_key = "-----BEGIN " + "PRIVATE KEY-----abc-----END " + "PRIVATE KEY-----"
        sensitive_evidence = ["password=" + "report-canary", "Authorization: Bearer " + "report-canary",
                              private_key, authentication_url]
        units[0]["review_history"] = [{"round": 1, "changed_paths": ["/outside/file"], "outcome": "fail",
                                        "verifier": {"evidence": sensitive_evidence, "unknown_nested": "omit"}, "scope_reviewer": {}}]
        units[0]["improvement_history"] = [{"after_round": 1, "kind": "terra_recovery", "root_cause": "cause", "hypothesis": "hypothesis", "action": "action", "evidence": ["proof"]}]
        run["deviations"] = [{"summary": "drift", "root_cause": "cause", "impact": "impact", "prevention": "prevention", "next_action": "next"}]
        payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
        digest = report.canonical_payload_digest(payload)
        data = report.render_report(payload, digest).decode()
        self.assertIn("$WORKSPACE", data)
        self.assertIn("[external reference]", data)
        self.assertIn("&lt;script&gt;", data)
        self.assertIn("password=[redacted]", data)
        self.assertIn("Authorization: Bearer [redacted]", data)
        self.assertNotIn("topsecret", data)
        self.assertNotIn("PRIVATE KEY-----abc", data)
        self.assertNotIn("user:pass@", data)
        self.assertNotIn("unknown_nested", data)
        self.assertNotIn("do not include", data)
        self.assertNotIn("ignore this", data)
        self.assertNotIn("raw_log", data)
        self.assertIn("[redacted credential URL]", data)
        self.assertIn("root_cause=cause", data)
        self.assertIn("hypothesis=hypothesis", data)
        self.assertIn("next", data)

    def test_payload_digest_is_canonical_and_validator_rejects_bad_report(self) -> None:
        contract, run, units, events, digests = self.fixture()
        one = report.build_payload("/tmp/work", contract, run, units, events, digests)
        two = copy.deepcopy(one)
        two = {key: two[key] for key in reversed(list(two))}
        self.assertEqual(report.canonical_payload_digest(one), report.canonical_payload_digest(two))
        with self.assertRaises(ValueError):
            report.validate_report_bytes(b"<main id=\"report\"></main>", "sha256:" + "e" * 64, one)

    def test_report_data_ledger_is_visible_complete_and_bound(self) -> None:
        contract, run, units, events, digests = self.fixture()
        payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
        payload["ledger-probe"] = {"a/b": "", "~key": 7, "flag": True, "none": None, "empty": [], "obj": {}}
        digest = report.canonical_payload_digest(payload)
        data = report.render_report(payload, digest)
        text = data.decode()
        self.assertIn("/ledger-probe/a~1b", text)
        self.assertIn("/ledger-probe/~0key", text)
        for literal in ('&quot;&quot;', "7", "true", "null", "[]", "{}"): self.assertIn(literal, text)
        self.assertNotIn('application/json', text)
        self.assertNotIn('#report-data{display:none', text)
        self.assertNotIn('.evidence-content{display:none', text)
        self.assertIn('<details id="evidence-vault" class="evidence-vault">', text)
        self.assertTrue(report.validate_report_bytes(data, digest, payload))
        block = report._payload_ledger_block(payload).encode()
        with self.assertRaises(ValueError):
            report.validate_report_bytes(data.replace(block, b"", 1), digest, payload)
        with self.assertRaises(ValueError):
            report.validate_report_bytes(data.replace(b"/ledger-probe/a~1b", b"/ledger-probe/changed", 1), digest, payload)
        with self.assertRaises(ValueError):
            report.validate_report_bytes(data.replace(b"</main>", block + b"</main>"), digest, payload)
        changed = copy.deepcopy(payload)
        changed["ledger-probe"]["none"] = "changed"
        with self.assertRaises(ValueError):
            report.validate_report_bytes(data, digest, changed)

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
        self.assertIn("검증된 테스트 영수증 수", data)
        self.assertIn("overflow-wrap:anywhere", data)
        self.assertIn("receipt-list", data)
        self.assertNotIn("subprocess-stdout-canary", data)

    def test_all_report_text_is_redacted_and_validator_rejects_raw_html(self) -> None:
        contract, run, units, events, digests = self.fixture()
        canary = "AWS_SECRET_ACCESS_KEY:=do-not-echo"
        self.assertEqual(report._text("secret handling"), "secret handling")
        contract["goals"] = [canary]
        run["deviations"] = [{"summary": canary, "root_cause": canary, "impact": canary,
                              "prevention": canary, "evidence": [canary]}]
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

    def test_validator_does_not_join_distinct_attribute_values(self) -> None:
        contract, run, units, events, digests = self.fixture()
        payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
        digest = report.canonical_payload_digest(payload)
        data = report.render_report(payload, digest).replace(
            b"</main>", b'<div class="Authorization:" aria-live="Basic [redacted]"></div></main>'
        )
        self.assertTrue(report.validate_report_bytes(data, digest, payload))

    def test_report_credential_segments_cover_pua_and_boundary_rules(self) -> None:
        markers = ("\ue000", "\uf8ff", "\U000f0000", "\U00100000", "\ufffe", "\uffff",
                   "\x00", "\x1f", "\x7f", "\u200b", "\u200d", "\u2060")
        keys = ("CLIENT-SECRET", "github-token", "private key")
        operators = ("=", ":=", ":")
        values = [f"{keys[index % 3]}{operators[index % 3]}pre{marker}report-segment-canary{marker}post"
                  for index, marker in enumerate(markers)]
        values += ["CLIENT-SECRET=[redacted]\ue000report-segment-canary",
                   "github-token:=\uf8ffreport-segment-canary"]
        for value in values:
            with self.subTest(value=repr(value)):
                cleaned = report._text(value)
                self.assertNotIn("report-segment-canary", cleaned)
                self.assertEqual(report._text(cleaned), cleaned)
        for value in ("secret handling", "token usage unavailable", "client-secretary=value", "tokenization=value"):
            self.assertFalse(report.contains_sensitive_data(value))
        contract, run, units, events, digests = self.fixture()
        run["deferred_security"] = [{"summary": "segment probes", "reason": values[0],
                                      "next_action": "wait", "evidence": values}]
        payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
        digest = report.canonical_payload_digest(payload)
        data = report.render_report(payload, digest)
        self.assertNotIn("report-segment-canary", json.dumps(payload, ensure_ascii=False))
        self.assertNotIn("report-segment-canary", data.decode())
        self.assertTrue(report.validate_report_bytes(data, digest, payload))
        for fragment in (
                "CLIENT-SECRET:<span></span>report-inline-canary",
                "github-token:<span><small></small></span>report-inline-canary"):
            with self.subTest(fragment=fragment):
                injected = data.replace(b"</main>", (fragment + "</main>").encode())
                with self.assertRaisesRegex(ValueError, "credential-bearing"):
                    report.validate_report_bytes(injected, digest, payload)
        for fragment in ("CLIENT-SECRET:<div>report-block-canary</div>",
                         "github-token:<p>report-block-canary</p>",
                         "private key:<br>report-block-canary"):
            injected = data.replace(b"</main>", (fragment + "</main>").encode())
            self.assertTrue(report.validate_report_bytes(injected, digest, payload))
        attrs = data.replace(b"</main>", b'<div class="CLIENT-SECRET:" aria-live="report-attr-canary"></div></main>')
        self.assertTrue(report.validate_report_bytes(attrs, digest, payload))
        escaped = data.replace(b"</main>", b"&lt;div&gt;CLIENT-SECRET=report-escaped-canary&lt;/div&gt;</main>")
        with self.assertRaisesRegex(ValueError, "credential-bearing"):
            report.validate_report_bytes(escaped, digest, payload)
        raw = data.replace(b"</main>", b'<p class="CLIENT-SECRET=report-raw-canary"></p></main>')
        with self.assertRaisesRegex(ValueError, "credential-bearing"):
            report.validate_report_bytes(raw, digest, payload)

    def test_header_credential_whitespace_has_state_report_parity(self) -> None:
        whitespace = ("", " ", "\t", "\n", "\r", "\r\n", "\f", "\v", "\u00a0",
                      "\u2028", "\u2029", "\x1f")
        keys = ("private-key", "private key", "x-api-key", "x api key", "x_api_key",
                "cookie", "authorization", "proxy-authorization")
        operators = ("=", ":=", ":")
        canary = "parity-header-canary"
        end_to_end = []
        for key in keys:
            separator = next((item for item in ("-", " ", "_") if item in key), None)
            for operator in operators:
                for gap in whitespace:
                    variants = [f"{key}{gap}{operator}{canary}",
                                f"{key}{operator}{gap}{canary}",
                                f"{key}{operator}pre{gap}{canary}{gap}post"]
                    if separator:
                        variants.append(f"{key.replace(separator, gap, 1)}{operator}{canary}")
                    for value in variants:
                        state_result = state.contains_sensitive_data(value)
                        report_result = report.contains_sensitive_data(value)
                        self.assertEqual(state_result, report_result, repr(value))
                        if state_result and canary not in report._text(value):
                            end_to_end.append(value)
        contract, run, units, events, digests = self.fixture()
        run["deferred_security"] = [{"summary": "header parity", "reason": end_to_end[0],
                                      "next_action": "wait", "evidence": end_to_end[:24]}]
        payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
        digest = report.canonical_payload_digest(payload)
        data = report.render_report(payload, digest)
        self.assertNotIn(canary, json.dumps(payload, ensure_ascii=False))
        self.assertNotIn(canary, data.decode())
        self.assertTrue(report.validate_report_bytes(data, digest, payload))
        attrs = data.replace(b"</main>", b'<div class="Private-Key:" aria-live="allowed"></div></main>')
        self.assertTrue(report.validate_report_bytes(attrs, digest, payload))

    def test_validator_rejects_extra_static_fragments(self) -> None:
        contract, run, units, events, digests = self.fixture()
        payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
        digest = report.canonical_payload_digest(payload)
        data = report.render_report(payload, digest)
        fragments = (
            '<link rel="stylesheet" href="https://evil.invalid/injected.css">',
            '<script type="module">document.body.dataset.injected="1";</script>',
            f'<meta name="hwahap-source-sha256" content="{digest}">',
            '<section id="summary"></section>',
            '<style>body{display:none}</style>',
        )
        for fragment in fragments:
            with self.subTest(fragment=fragment):
                injected = data.replace(b"</main>", (fragment + "</main>").encode())
                with self.assertRaises(ValueError):
                    report.validate_report_bytes(injected, digest, payload)

    def test_escaped_user_markup_remains_valid_report_content(self) -> None:
        contract, run, units, events, digests = self.fixture()
        run["goal_link"]["current"]["reason"] = '<img src="safe"> <!-- harmless text -->'
        payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
        digest = report.canonical_payload_digest(payload)
        data = report.render_report(payload, digest)
        text = data.decode()
        self.assertIn("&lt;img src=&quot;safe&quot;&gt;", text)
        self.assertIn("&lt;!-- harmless text --&gt;", text)
        self.assertTrue(report.validate_report_bytes(data, digest, payload))

    def test_curl_and_secret_assignments_are_redacted_in_payload_and_html(self) -> None:
        contract, run, units, events, digests = self.fixture()
        continuation = "curl " + chr(92) + "\n  --user audit:linecase URL"
        continuation_crlf = "curl " + chr(92) + "\r\n  --user audit:crlfcase URL"
        values = ("curl -u user:pass URL", "curl -uuser:pass URL", continuation,
                  continuation_crlf,
                  "curl --user user:pass", "curl --user=user:pass",
                  "curl -Uuser:pass URL", "curl --proxy-user user:pass",
                  "curl --proxy-user=user:pass", "curl --oauth2-bearer supersecret",
                  "curl --oauth2-bearer=supersecret", "SECRET_KEY=supersecret",
                  "SERVICE_SECRET_KEY:=supersecret")
        run["deviations"] = [{"summary": value, "root_cause": "context",
                              "impact": "impact", "prevention": "prevention",
                              "evidence": ["evidence"]} for value in values]
        run["improvement_candidates"] = [{"status": "proposed", "summary": value,
                                           "evidence": ["evidence"],
                                           "expected_effect": "effect",
                                           "next_action": "action"} for value in values]
        payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
        encoded = json.dumps(payload, ensure_ascii=False)
        digest = report.canonical_payload_digest(payload)
        text = report.render_report(payload, digest).decode()
        for raw in ("user:pass", "supersecret", "audit:linecase", "audit:crlfcase"):
            self.assertNotIn(raw, encoded)
            self.assertNotIn(raw, text)
        for marker in ("curl -u [redacted] URL", "curl -u[redacted] URL",
                       "curl --user [redacted] URL",
                       "curl --user [redacted]", "curl --user=[redacted]",
                       "curl -U[redacted] URL", "curl --proxy-user [redacted]",
                       "curl --proxy-user=[redacted]", "curl --oauth2-bearer [redacted]",
                       "curl --oauth2-bearer=[redacted]", "SECRET_KEY=[redacted]",
                       "SERVICE_SECRET_KEY:=[redacted]"):
            self.assertIn(marker, encoded)
            self.assertIn(marker, text)
        self.assertTrue(report.validate_report_bytes(text.encode(), digest, payload))
        harmless = "curlish --user documentation"
        self.assertFalse(report.contains_sensitive_data(harmless))
        self.assertEqual(report._text(harmless), harmless)

    def test_prefixed_assignment_credentials_share_state_grammar_and_redaction(self) -> None:
        values = ("CLIENT-SECRET=report-assignment-sentinel", "github-token:=report-assignment-sentinel",
                  "service-password: report-assignment-sentinel", "client secret=report-assignment-sentinel",
                  "x-api-key=report-assignment-sentinel", "private key=report-assignment-sentinel",
                  "client-secret=\nreport-assignment-sentinel", "client-secret=\r\nreport-assignment-sentinel",
                  "client-secret=\rreport-assignment-sentinel", "client-secret=\\\nreport-assignment-sentinel",
                  "client\fsecret=report-assignment-sentinel", "client\vsecret=report-assignment-sentinel",
                  "client\u00a0secret=report-assignment-sentinel",
                  "client-secret=[redacted] report-assignment-sentinel",
                  "client-secret=[redacted]\r\n\tresponse=report-assignment-sentinel",
                  "CLIENT-SECRET=<report-assignment-sentinel>",
                  "github-token:=pre<report-assignment-sentinel>post",
                  "service-password:\"<report-assignment-sentinel>\"",
                  "client secret: <report-assignment-sentinel>",
                  "x-api-key=<report-assignment-sentinel>", "private key:=<report-assignment-sentinel>")
        for value in values:
            with self.subTest(value=value):
                self.assertTrue(report.contains_sensitive_data(value))
                cleaned = report._text(value)
                self.assertNotIn("report-assignment-sentinel", cleaned)
                self.assertEqual(report._text(cleaned), cleaned)
        for value in ("secret handling", "token usage unavailable", "client-secretary=value", "tokenization=value"):
            self.assertFalse(report.contains_sensitive_data(value))
            self.assertEqual(report._text(value), value)
        self.assertFalse(report.contains_sensitive_data("client-secret=[redacted]"))
        self.assertEqual(report._text("client-secret=[redacted]"), "client-secret=[redacted]")
        contract, run, units, events, digests = self.fixture()
        run["deferred_security"] = [{"summary": "assignment probes", "reason": values[0],
                                      "next_action": "wait", "evidence": list(values)}]
        payload = report.build_payload("/tmp/work", contract, run, units, events, digests)
        encoded = json.dumps(payload, ensure_ascii=False)
        digest = report.canonical_payload_digest(payload)
        data = report.render_report(payload, digest)
        self.assertNotIn("report-assignment-sentinel", encoded)
        self.assertNotIn("report-assignment-sentinel", data.decode())
        self.assertTrue(report.validate_report_bytes(data, digest, payload))
        injected = data.replace(b'<main id="report">',
                                b'<main id="report" class="CLIENT-SECRET=report-assignment-sentinel">')
        with self.assertRaises(ValueError):
            report.validate_report_bytes(injected, digest, payload)

    def test_shared_engine_maps_obfuscated_keys_and_overlapping_spans(self) -> None:
        marker = "credential-engine-canary"
        obfuscators = ("\u200b", "\ue000", "\ufffe", "\x1f", "\u2060", "\u2028", "\u2029")
        for key in ("CLIENT-SECRET", "github-token", "service-password", "private key"):
            for obfuscator in obfuscators:
                with self.subTest(key=key, obfuscator=repr(obfuscator)):
                    raw_key = obfuscator.join(key)
                    value = f"{raw_key}{obfuscator}:={obfuscator}pre<{marker}>{obfuscator}post"
                    self.assertTrue(state.contains_sensitive_data(value))
                    self.assertTrue(report.contains_sensitive_data(value))
                    cleaned = report._text(value)
                    self.assertNotIn(marker, cleaned)
                    self.assertEqual(report._text(cleaned), cleaned)
        for value in ("secret handling", "token usage unavailable", "client-secretary=value", "😀 multilingual 텍스트"):
            self.assertFalse(state.contains_sensitive_data(value))
            self.assertFalse(report.contains_sensitive_data(value))

    def test_shared_engine_dual_views_cover_every_obfuscator_class(self) -> None:
        marker = "dual-view-canary"
        state._ensure_dependencies()
        engine = state._dependency_modules[1]
        codepoints = (0x00AD, 0x034F, 0x061C, 0x115F, 0x1160, 0x17B4, 0x17B5,
                      0x180B, 0x200B, 0x2028, 0x2029, 0x2060, 0x3164, 0xFE00,
                      0xFE0F, 0xFFA0, 0xE0100, 0x001F, 0xE000, 0xFDD0, 0xFFFE, 0x1FFFE)
        for codepoint in codepoints:
            separator = chr(codepoint)
            for key in (f"client{separator}secret", f"client-se{separator}cret"):
                value = f"{key}{separator}:={separator}pre<{marker}>{separator}post"
                with self.subTest(codepoint=hex(codepoint), key=key):
                    findings = engine.findings(value)
                    self.assertTrue(state.contains_sensitive_data(value))
                    self.assertTrue(report.contains_sensitive_data(value))
                    self.assertEqual(len(findings), len({(item.kind, item.start, item.end, item.value_start, item.value_end, item.scheme) for item in findings}))
                    self.assertNotIn(marker, report._text(value))
                    self.assertEqual(report._text(report._text(value)), report._text(value))
                    raw_payload = report.canonical_payload_bytes({"evidence": value})
                    with self.assertRaises(report.HwahapReportError):
                        report.validate_report_data_bytes(raw_payload, {"evidence": value}, report.canonical_payload_digest({"evidence": value}))
        for value in ("Authorization: Basic [redacted]", "Proxy-Authorization: Digest [redacted]",
                      "client-secret=[redacted]", "token_total=3", "😀 variation\ufe0f"):
            self.assertFalse(state.contains_sensitive_data(value))
            self.assertFalse(report.contains_sensitive_data(value))

    def test_shared_engine_keeps_dropped_first_view_for_leading_obfuscators(self) -> None:
        state._ensure_dependencies()
        engine = state._dependency_modules[1]
        for raw, expected_kind, expected_text, expected_value in (
            ("\u200bclient-secret=span-canary", "assignment", "client-secret=span-canary", "span-canary"),
            ("\u200bAuthorization: Bearer span-canary", "auth", "Authorization: Bearer span-canary", "Bearer span-canary"),
        ):
            with self.subTest(raw=raw):
                normalized = engine.normalized_text(raw)
                matches = engine.findings(raw)
                finding = next(item for item in matches if item.kind == expected_kind)
                self.assertEqual(normalized[finding.normalized_start:finding.normalized_end], expected_text)
                self.assertEqual(normalized[finding.normalized_value_start:finding.normalized_value_end], expected_value)
                self.assertGreaterEqual(finding.normalized_start, 0)
                self.assertLessEqual(finding.normalized_end, len(normalized))
                self.assertGreaterEqual(finding.normalized_value_start, 0)
                self.assertLessEqual(finding.normalized_value_end, len(normalized))
                self.assertEqual(raw[finding.start:finding.end], raw[1:])
                self.assertIn("span-canary", raw[finding.value_start:finding.value_end])
                cleaned = engine.redact(raw)
                self.assertNotIn("span-canary", cleaned)
                self.assertEqual(engine.redact(cleaned), cleaned)

    def test_redaction_engine_is_loaded_from_sibling_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "hwahap_redaction.py").write_text(
                "def contains_sensitive_data(value): return False\n", encoding="utf-8")
            previous_cwd = os.getcwd()
            previous = sys.modules.get("hwahap_redaction")
            os.chdir(directory)
            sys.modules["hwahap_redaction"] = object()
            try:
                for name, path in (("fresh_state", state.__file__), ("fresh_report", report.__file__)):
                    spec = importlib.util.spec_from_file_location(name, path)
                    self.assertIsNotNone(spec)
                    loaded = importlib.util.module_from_spec(spec)
                    assert spec and spec.loader
                    spec.loader.exec_module(loaded)
                    self.assertTrue(loaded.contains_sensitive_data("client_secret=sibling-canary"))
            finally:
                os.chdir(previous_cwd)
                if previous is None:
                    sys.modules.pop("hwahap_redaction", None)
                else:
                    sys.modules["hwahap_redaction"] = previous

    def test_standalone_provider_and_high_entropy_tokens_are_redacted(self) -> None:
        provider_tokens = (
            "gh" + "p_" + "A1" * 18,
            "sk-" + "proj-" + "aB3_" * 6,
            "xox" + "b-" + "Ab3" * 8,
            "npm" + "_" + "Ab3" * 7,
            "sk_" + "live_" + "Ab3" * 6,
            "AI" + "za" + "Ab3_" * 8 + "Ab3",
            "AK" + "IA" + "A1" * 8,
            "Ab3dEf5h" + "Ij7kLm9n" + "Op2qRs4t" + "Uv6wXy8z+/=",
        )
        for token in provider_tokens:
            with self.subTest(token_type=token[:4]):
                self.assertTrue(state.contains_sensitive_data(token))
                self.assertTrue(report.contains_sensitive_data(token))
                self.assertNotIn(token, report._text(token))
        for safe in ("token_total=3", "a" * 40, "sha256:" + "a" * 64):
            self.assertFalse(state.contains_sensitive_data(safe))
            self.assertFalse(report.contains_sensitive_data(safe))


if __name__ == "__main__":
    unittest.main()
