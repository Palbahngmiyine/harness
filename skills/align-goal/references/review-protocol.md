# Review protocol

## Ambiguity auditor

canonical contract와 repository evidence만 입력으로 주고, 이전 대화·작성자의 reasoning은 주지 않는다. 정확한 output은 다음이다.

```json
{
  "new_material_choices": [],
  "counterexamples": [],
  "contradictions": [],
  "invalid_forced_consequences": [],
  "invalid_local_coding": [],
  "unexamined_surfaces": []
}
```

각 finding은 관련 ID와 서로 다른 두 구현이 가능해지는 구체적 반례를 가진다. 하나라도 있으면 C 또는 O로 승격하고 `resolve_findings` 또는 `ask_choices`로 돌아간다. auditor PASS는 미래의 모든 선택을 수학적으로 증명하지 않는다.

## Cold consumer

이전 대화·reasoning·recommendation 없이 canonical contract와 지정 repository context만 주고, 구현하지 않고 선택 없는 계획을 작성한다. 정확한 receipt output은 다음이다.

```json
{
  "steps": [{"step": "...", "spec_ids": ["S1"], "acceptance_ids": ["A1"], "unit_ids": ["U1"]}],
  "required_user_choices": [],
  "implicit_assumptions": [],
  "contradictions": [],
  "underspecified_clauses": [],
  "unmapped_spec_ids": [],
  "local_choices": []
}
```

각 step은 `step`, `spec_ids`, `acceptance_ids`, `unit_ids`를 가지며 존재하는 S/A/U만 참조한다. 전체 S/A/U를 빠짐없이 덮어야 한다. blocker는 required_user_choices, implicit_assumptions, contradictions, underspecified_clauses, unmapped_spec_ids다. 이 배열들은 모두 비어야 PASS다. local_choices는 nonempty여도 proof가 완전하면 PASS다.

각 local_choices element는 아래 exact key를 갖는다.

```json
{
  "id": "LC1",
  "description": "private helper inline/split",
  "unit_id": "U1",
  "same_observable_behavior": {"satisfied": true, "evidence": "..."},
  "unchanged_named_surfaces": {"satisfied": true, "evidence": "..."},
  "no_system_impact": {"satisfied": true, "evidence": "..."},
  "private_unit_only": {"satisfied": true, "evidence": "..."},
  "reversible_without_spec_change": {"satisfied": true, "evidence": "..."}
}
```

proof 하나라도 빠지거나 satisfied가 false면 material choice 후보로 승격한다. unknown reference, plural `unit_ids` 누락, incomplete full coverage도 FAIL이다.

## Digest-bound reviews and confirmations

정규화된 spec_projection의 sha256과 repository_context object의 sha256을 모든 receipt에 저장한다. RFC3339 timestamp가 서로 다른 offset을 사용해도 같은 instant로 비교한다. 어느 digest든 현재 값과 다르면 receipt는 stale이고 해당 review를 다시 실행한다. C의 affected_spec_ids, affected_acceptance_ids, affected_unit_ids는 계산된 reverse 목록과 정확히 일치해야 한다. choice 변경은 그 reverse 목록의 S/A/U와 관련 receipt를 stale로 만들고, stale receipt는 gate의 fresh review를 충족하지 못한다. receipt timestamp만 바뀌면 review freshness는 유지되며, review output 변경은 confirmation만 stale로 만든다.

alignment summary confirmation은 다음 shape다.

```json
{
  "confirmation_id": "UC1",
  "exact_response": "요약이 내 답을 정확히 반영한다",
  "turn_id": "turn-1",
  "confirmed_at": "2026-08-31T12:00:00+09:00",
  "spec_digest": "sha256:...",
  "repository_context_digest": "sha256:...",
  "ambiguity_review_id": "R1",
  "ambiguity_receipt_digest": "sha256:..."
}
```

handoff document confirmation은 위 필드에 `cold_review_id`, `cold_receipt_digest`를 추가한다. 두 confirmation ID는 달라야 하며 handoff confirmation은 alignment confirmation의 confirmed_at 이후이고 cold receipt의 generated_at 이후에 생성돼야 한다. confirmations는 top-level spec projection에 포함하지 않는다.

## Gates and computed next_action

`aligned`는 모든 C가 user-bound confirmed 또는 valid superseded이고, open O가 0이고, 12 surface가 current confirmed C 또는 immutable F로 닫히고, fresh ambiguity PASS와 alignment summary confirmation이 있을 때만 가능하다. `handoff_ready`는 frontmatter의 `alignment_status=aligned`와 `handoff_status=ready`를 명시적으로 요구하며, implementation target, session complete, S provenance·S-A-U mapping 완전, U cycle/orphan 0, placeholder·assumption·open O 0, fresh cold PASS, cold 이후 fresh handoff confirmation을 추가로 요구한다. planning state이며 실행 권한이 아니다.

validator는 문서에 next_action을 저장하지 않는다. parse 가능한 문서에서 session_status가 paused면 `pause`를 반환한다. 그 외 첫 조건 하나만 반환한다.

1. repository evidence/facts missing or unusable → `research_facts`
2. surface missing/unclassified/invalid resolution → `map_choices`
3. candidate/asked/vague/incomplete C 또는 open choice O → `ask_choices`
4. S/A/U trace, mapping, graph incomplete → `compile_spec`
5. ambiguity receipt missing/stale → `run_ambiguity_audit`
6. ambiguity findings 또는 conflict O → `resolve_findings`
7. alignment confirmation missing/stale → `request_final_confirmation`
8. decision target gate satisfied → `complete`
9. implementation cold receipt missing/stale → `run_cold_consumer`
10. cold blocker/incomplete local proof → `resolve_findings`
11. handoff confirmation missing/stale → `request_final_confirmation`
12. all gates satisfied → `complete`

허용 vocabulary는 `research_facts`, `map_choices`, `ask_choices`, `compile_spec`, `run_ambiguity_audit`, `run_cold_consumer`, `resolve_findings`, `request_final_confirmation`, `complete`, `pause`다. 총 라운드 제한은 없고 dependency 없는 질문은 라운드당 최대 8개, 4라운드마다 checkpoint다. complete는 gate 충족 때만 가능하며 스스로 임의 종료하지 않는다. 구현 중 새 material choice가 나오면 구현을 중단하고 새 C로 되돌린다.

## Deterministic validator semantics

validator는 UTF-8/usage 실패를 exit 2로, validation failure를 exit 1로, pass를 exit 0으로 반환한다. 정확한 frontmatter 9 key와 type/enum/RFC3339, canonical fence 1개를 검사하고, duplicate-key detecting JSON loader로 duplicate key와 NaN/Infinity를 거부한다. exact top-level/entry key·type, frontmatter/contract target·revision, register prefix와 global ID uniqueness를 검사한다. C state/null 규칙, alternatives/value, vague response, policy/supersession, question round/checkpoint와 dependency를 검사한다.

validator는 exact 12 DS name과 resolution, S provenance, S-A-U mapping과 reverse affected lists, U DAG/order/cycle/orphan, O 상태를 계산한다. orphan에는 S/A가 없는 U, U에 매핑되지 않은 S/A, unknown reference/dependency가 포함된다. computed digest, stale receipt/confirmation, review output과 full coverage도 검사한다. frontmatter가 aligned 또는 ready를 주장하면 CLI가 structural이어도 해당 gate를 강제한다. 구조적으로 유효한 finding receipt는 structural에서 허용하지만 aligned/ready에서는 실패한다. placeholder/assumption gate 검사는 planner-authored contract text와 projection에만 적용하고, observed fact의 literal observation/source text는 해당 단어가 있다는 이유만으로 오탐하지 않는다.

`structural`은 shape/type/ID/reference/digest shape를 검사하고 candidate/asked C, open O, missing receipt, finding receipt를 허용한다. `aligned`는 valid confirmed/superseded C, open O 0, 12 surface closure, fresh ambiguity PASS, fresh alignment summary를 요구한다. `handoff-ready`는 aligned, implementation target, session complete, nonempty S/A/U, 완전한 provenance와 mapping, cycle/orphan 0, open O·placeholder·assumption 0, fresh cold PASS, cold 이후 handoff confirmation을 요구한다. alignment confirmation만으로 handoff-ready가 되지 않으며 cold 이후 별도 confirmation이 필요하다.
