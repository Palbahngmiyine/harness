#!/usr/bin/env python3
"""Focused tests for grill-prfaq PR/FAQ structural validation."""

from __future__ import annotations

import importlib.util
import re
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("validate_prfaq.py")
SKILL_DIR = MODULE_PATH.parent.parent
SPEC = importlib.util.spec_from_file_location("validate_prfaq", MODULE_PATH)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)

RULE = (
    "**작성 규칙** — 확인된 사실만 산문으로 쓴다. 사용자만 쓸 수 있는 자리는 `【 】`로 "
    "비워 둔다. 사용자의 말은 「 」 안에 원문 그대로 적는다."
)

HYPOTHESIS = f"""---
title: 온콜 인수인계 메모 자동화
status: hypothesis
customer: internal
created: 2026-08-23
updated: 2026-08-23
confirmed_at:
---

# 온콜 인수인계 메모 자동화

{RULE}

## 1. 가설

### F1. 고객
**결정** 「주간 온콜을 넘기는 SRE」 (R2)

### F2. 문제
**결정** 「인수인계 때 지난주 알림 맥락이 사라진다」 (R1)

### F3. 핵심 이익
**가정** 인수인계 회의가 짧아진다 — 검증 계획: 2주간 회의 시간 기록

### F4. 근거
**사실** 지난 4주 알림 기록에 같은 원인이 세 번 반복됐다 — 출처: runbooks/oncall-log.md, 2026-08-23

### F5. 경험
**프로토타입 필요** — 보류 (R2)

## 2. FAQ

### F6. 기존 runbook과 어떻게 다른가
**결정** 「runbook은 절차, 이건 지난주 맥락」 (R2)

## 3. 범위 밖

- F5 — **프로토타입 필요**

## 4. 게이트

| 차원 | 등급 | 근거 |
|---|---|---|
| 고객 | | |
| 문제 | | |
| 핵심 이익 | | |
| 근거 | | |
| 경험 | | |

- 프론티어 재도출:
- 검증기:
- 확인 문장:

## 5. PR

(비어 있음 — status가 prfaq가 된 뒤에 쓴다)
"""

PR_PROSE = (
    "온콜 인수인계 메모가 지난주 맥락을 자동으로 남긴다.\n\n"
    "주간 온콜을 넘기는 SRE는 인수인계 때 지난주 알림 맥락을 잃는다 (F2). "
    "같은 원인이 4주 동안 세 번 반복됐다 (F4). 【왜 지금인가】"
)

GATE_FILLED = (
    HYPOTHESIS.replace(
        "**가정** 인수인계 회의가 짧아진다 — 검증 계획: 2주간 회의 시간 기록",
        "**가정** 인수인계 회의가 짧아진다 — **사용자 수용** 「측정 없이 간다」",
    )
    .replace("| 고객 | | |", "| 고객 | solid | F1 |")
    .replace("| 문제 | | |", "| 문제 | solid | F2, F6 |")
    .replace("| 핵심 이익 | | |", "| 핵심 이익 | solid | F3 |")
    .replace("| 근거 | | |", "| 근거 | outstanding | F4 |")
    .replace("| 경험 | | |", "| 경험 | borderline | F5 |")
    .replace("- 프론티어 재도출:\n", "- 프론티어 재도출: 비어 있음 (R3)\n")
    .replace("- 확인 문장:\n", "- 확인 문장: 「예」 (2026-08-24)\n")
)

PRFAQ = (
    GATE_FILLED.replace("status: hypothesis", "status: prfaq")
    .replace("confirmed_at:\n", "confirmed_at: 2026-08-24\n")
    .replace("- 검증기:\n", "- 검증기: 통과, 2026-08-24\n")
    .replace("(비어 있음 — status가 prfaq가 된 뒤에 쓴다)", PR_PROSE)
)


class ValidatePrfaqTests(unittest.TestCase):
    def errors(self, text: str) -> list[str]:
        errors, _ = VALIDATOR.validate(text)
        return errors

    # --- 정상 통과 ---

    def test_valid_hypothesis_passes_with_counts(self) -> None:
        errors, summary = VALIDATOR.validate(HYPOTHESIS)
        self.assertEqual(errors, [])
        self.assertEqual(
            summary,
            {
                "status": "hypothesis",
                "facts": 1,
                "decisions": 3,
                "assumptions": 1,
                "parked": 1,
                "faq": 1,
                "open": 0,
            },
        )

    def test_valid_prfaq_passes(self) -> None:
        self.assertEqual(self.errors(PRFAQ), [])

    def test_rejected_keeps_placeholder(self) -> None:
        text = HYPOTHESIS.replace("status: hypothesis", "status: rejected")
        self.assertEqual(self.errors(text), [])

    # --- frontmatter ---

    def test_rejects_unknown_frontmatter_key(self) -> None:
        text = HYPOTHESIS.replace("confirmed_at:\n", "confirmed_at:\nrounds: 3\n")
        self.assertTrue(any("unknown keys" in e for e in self.errors(text)))

    def test_hypothesis_with_confirmed_at(self) -> None:
        text = HYPOTHESIS.replace("confirmed_at:\n", "confirmed_at: 2026-08-24\n")
        self.assertTrue(any("confirmed_at must be empty" in e for e in self.errors(text)))

    def test_prfaq_without_confirmed_at(self) -> None:
        text = PRFAQ.replace("confirmed_at: 2026-08-24", "confirmed_at:")
        self.assertTrue(any("requires confirmed_at" in e for e in self.errors(text)))

    # --- 태그 줄 ---

    def test_item_without_tag_line(self) -> None:
        text = HYPOTHESIS.replace("**결정** 「runbook은 절차, 이건 지난주 맥락」 (R2)", "runbook과 다르다")
        self.assertTrue(any("F6 must have exactly one tag line" in e for e in self.errors(text)))

    def test_fact_without_source(self) -> None:
        text = HYPOTHESIS.replace(" — 출처: runbooks/oncall-log.md, 2026-08-23", "")
        self.assertTrue(any("F4 사실 needs" in e for e in self.errors(text)))

    def test_decision_must_quote_verbatim(self) -> None:
        text = HYPOTHESIS.replace("「주간 온콜을 넘기는 SRE」", "주간 온콜을 넘기는 SRE")
        self.assertTrue(any("F1 결정 must quote" in e for e in self.errors(text)))

    def test_decision_requires_round_marker(self) -> None:
        text = HYPOTHESIS.replace("**결정** 「주간 온콜을 넘기는 SRE」 (R2)", "**결정** 「주간 온콜을 넘기는 SRE」")
        self.assertTrue(any("F1 결정 needs a round marker" in e for e in self.errors(text)))

    def test_assumption_without_plan(self) -> None:
        text = HYPOTHESIS.replace(" — 검증 계획: 2주간 회의 시간 기록", "")
        self.assertTrue(any("F3 가정 needs" in e for e in self.errors(text)))

    def test_accepted_assumption_is_allowed(self) -> None:
        text = HYPOTHESIS.replace(
            "**가정** 인수인계 회의가 짧아진다 — 검증 계획: 2주간 회의 시간 기록",
            "**가정** 인수인계 회의가 짧아진다 — **사용자 수용** 「측정 없이 간다」",
        )
        self.assertEqual(self.errors(text), [])

    # --- F4 근거 슬롯 ---

    def test_evidence_slot_rejects_recommendation(self) -> None:
        text = HYPOTHESIS.replace(
            "**사실** 지난 4주 알림 기록에 같은 원인이 세 번 반복됐다 — 출처: runbooks/oncall-log.md, 2026-08-23",
            "**가정** 아마 반복될 것이다 — 검증 계획: 확인\n\n➡️ 추천: 반복된다고 본다",
        )
        self.assertTrue(any("F4 (근거)" in e for e in self.errors(text)))

    def test_f4_decision_rejects_option_letter(self) -> None:
        text = HYPOTHESIS.replace(
            "**사실** 지난 4주 알림 기록에 같은 원인이 세 번 반복됐다 — 출처: runbooks/oncall-log.md, 2026-08-23",
            "**결정** 「B」 (R1)",
        )
        self.assertTrue(any("not an option pick" in e for e in self.errors(text)))

    def test_root_slot_rejects_hidden_recommendation(self) -> None:
        text = HYPOTHESIS.replace(
            "**결정** 「주간 온콜을 넘기는 SRE」 (R2)",
            "**결정** 「주간 온콜을 넘기는 SRE」 (R2)\n➡️ 추천: 개발자까지 넓힌다",
        )
        self.assertTrue(any("F1 root slot may not hold" in e for e in self.errors(text)))

    # --- 보류와 범위 밖 ---

    def test_parked_root_slot_must_be_in_scope_section(self) -> None:
        text = HYPOTHESIS.replace("- F5 — **프로토타입 필요**\n", "")
        self.assertTrue(any("F5 is parked but not listed" in e for e in self.errors(text)))

    def test_parked_scope_check_is_not_substring(self) -> None:
        text = HYPOTHESIS.replace("- F5 — **프로토타입 필요**", "- F50 — **프로토타입 필요**")
        self.assertTrue(any("F5 is parked but not listed" in e for e in self.errors(text)))

    def test_customer_none_requires_out_of_scope_line(self) -> None:
        text = HYPOTHESIS.replace("customer: internal", "customer: none")
        self.assertTrue(any("customer=none requires" in e for e in self.errors(text)))
        fixed = text.replace("## 3. 범위 밖\n", "## 3. 범위 밖\n\n- 「해당 없음」 — Q0, R1")
        self.assertEqual(self.errors(fixed), [])

    def test_root_decision_may_not_be_not_applicable(self) -> None:
        text = HYPOTHESIS.replace("「주간 온콜을 넘기는 SRE」", "「해당 없음」")
        self.assertTrue(any("is not a settled decision" in e for e in self.errors(text)))

    # --- 열린 슬롯 ---

    def test_open_root_slot_allowed_before_gate(self) -> None:
        text = HYPOTHESIS.replace("**결정** 「주간 온콜을 넘기는 SRE」 (R2)\n", "")
        errors, summary = VALIDATOR.validate(text)
        self.assertEqual(errors, [])
        self.assertEqual(summary["open"], 1)

    def test_open_root_slot_must_be_blank(self) -> None:
        text = HYPOTHESIS.replace("**결정** 「주간 온콜을 넘기는 SRE」 (R2)", "SRE라고 한다")
        self.assertTrue(any("F1 has prose but no tag line" in e for e in self.errors(text)))

    def test_open_root_slot_is_rejected_once_gate_is_on(self) -> None:
        text = GATE_FILLED.replace("**결정** 「주간 온콜을 넘기는 SRE」 (R2)\n", "")
        self.assertTrue(any("F1 must have exactly one tag line" in e for e in self.errors(text)))

    # --- 게이트 검사 시점 ---

    def test_gate_is_checked_before_status_flips(self) -> None:
        text = GATE_FILLED.replace("| 고객 | solid | F1 |", "| 고객 | poor | F1 |")
        self.assertTrue(any("poor dimension" in e for e in self.errors(text)))

    def test_gate_step_four_state_passes_without_validator_line(self) -> None:
        self.assertEqual(self.errors(GATE_FILLED), [])

    def test_filled_table_without_confirmation_is_not_gated(self) -> None:
        text = (
            HYPOTHESIS.replace("| 고객 | | |", "| 고객 | solid | F1 |")
            .replace("| 핵심 이익 | | |", "| 핵심 이익 | poor | F3 |")
            .replace("- 프론티어 재도출:\n", "- 프론티어 재도출: 비어 있음 (R3)\n")
        )
        self.assertEqual(self.errors(text), [])

    # --- 게이트 표 ---

    def test_prfaq_with_poor_dimension(self) -> None:
        text = PRFAQ.replace("| 고객 | solid | F1 |", "| 고객 | poor | F1 |")
        self.assertTrue(any("poor dimension" in e for e in self.errors(text)))

    def test_prfaq_with_two_borderline_dimensions(self) -> None:
        text = PRFAQ.replace("| 고객 | solid | F1 |", "| 고객 | borderline | F1 |")
        self.assertTrue(any("more than one borderline" in e for e in self.errors(text)))

    def test_outstanding_requires_fact_evidence(self) -> None:
        text = PRFAQ.replace("| 고객 | solid | F1 |", "| 고객 | outstanding | F1 |")
        self.assertTrue(any("outstanding requires a 사실" in e for e in self.errors(text)))

    def test_gate_evidence_must_cite_existing_ids(self) -> None:
        text = PRFAQ.replace("| 고객 | solid | F1 |", "| 고객 | solid | F9 |")
        self.assertTrue(any("unknown F-ids [9]" in e for e in self.errors(text)))

    def test_gate_evidence_must_not_be_empty(self) -> None:
        text = PRFAQ.replace("| 고객 | solid | F1 |", "| 고객 | solid | 사용자 답 |")
        self.assertTrue(any("must cite at least one F-id" in e for e in self.errors(text)))

    def test_parked_slot_graded_solid_is_rejected(self) -> None:
        text = PRFAQ.replace("| 경험 | borderline | F5 |", "| 경험 | solid | F5 |")
        self.assertTrue(any("may not exceed borderline" in e for e in self.errors(text)))

    def test_assumption_without_acceptance_graded_solid_is_rejected(self) -> None:
        text = PRFAQ.replace(
            "**가정** 인수인계 회의가 짧아진다 — **사용자 수용** 「측정 없이 간다」",
            "**가정** 인수인계 회의가 짧아진다 — 검증 계획: 2주간 회의 시간 기록",
        )
        self.assertTrue(any("may not exceed borderline" in e for e in self.errors(text)))

    def test_fid_survives_korean_particles(self) -> None:
        text = PRFAQ.replace("| 근거 | outstanding | F4 |", "| 근거 | outstanding | F4로 확인 |")
        self.assertEqual(self.errors(text), [])
        text = PRFAQ.replace("| 고객 | solid | F1 |", "| 고객 | solid | F9와 F6 |")
        self.assertTrue(any("unknown F-ids [9]" in e for e in self.errors(text)))

    # --- 확인 문장과 검증기 줄 ---

    def test_prfaq_without_confirmation_sentence(self) -> None:
        text = PRFAQ.replace("- 확인 문장: 「예」 (2026-08-24)", "- 확인 문장:")
        self.assertTrue(any("확인 문장" in e for e in self.errors(text)))

    def test_confirmation_date_must_match_confirmed_at(self) -> None:
        text = PRFAQ.replace("- 확인 문장: 「예」 (2026-08-24)", "- 확인 문장: 「예」 (2026-08-01)")
        self.assertTrue(any("must equal confirmed_at" in e for e in self.errors(text)))

    def test_prfaq_validator_field_must_say_pass(self) -> None:
        text = PRFAQ.replace("- 검증기: 통과, 2026-08-24", "- 검증기: 실패")
        self.assertTrue(any("검증기" in e for e in self.errors(text)))

    def test_frontier_line_must_be_filled(self) -> None:
        text = PRFAQ.replace("- 프론티어 재도출: 비어 있음 (R3)", "- 프론티어 재도출:")
        self.assertTrue(any("프론티어 재도출" in e for e in self.errors(text)))

    # --- §5 PR ---

    def test_hypothesis_with_filled_pr(self) -> None:
        text = HYPOTHESIS.replace("(비어 있음 — status가 prfaq가 된 뒤에 쓴다)", "벌써 쓴 PR 문단.")
        self.assertTrue(any("must be exactly the placeholder" in e for e in self.errors(text)))

    def test_prfaq_pr_rejects_bullets(self) -> None:
        text = PRFAQ.replace("【왜 지금인가】", "【왜 지금인가】\n\n- 첫째 이유\n- 둘째 이유")
        self.assertTrue(any("must be prose" in e for e in self.errors(text)))

    def test_prfaq_pr_must_drop_placeholder(self) -> None:
        text = PRFAQ.replace(
            "온콜 인수인계 메모가",
            "(비어 있음 — status가 prfaq가 된 뒤에 쓴다)\n\n온콜 인수인계 메모가",
        )
        self.assertTrue(any("still holds the placeholder" in e for e in self.errors(text)))

    # --- 문서와의 일치 ---

    def test_reference_template_block_validates_once_dates_are_filled(self) -> None:
        template = SKILL_DIR / "references" / "prfaq-template.md"
        block = re.search(r"```markdown\n(.*?)```", template.read_text(encoding="utf-8"), re.S)
        assert block
        text = block.group(1).replace("YYYY-MM-DD", "2026-08-23")
        errors, summary = VALIDATOR.validate(text)
        self.assertEqual(errors, [])
        self.assertEqual(summary["open"], 5)

    def test_skill_md_embeds_the_same_template_block(self) -> None:
        pattern = re.compile(r"```markdown\n(.*?)```", re.S)
        skill_block = pattern.search((SKILL_DIR / "SKILL.md").read_text(encoding="utf-8"))
        ref_block = pattern.search(
            (SKILL_DIR / "references" / "prfaq-template.md").read_text(encoding="utf-8")
        )
        assert skill_block and ref_block
        self.assertEqual(skill_block.group(1), ref_block.group(1))


if __name__ == "__main__":
    unittest.main()
