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

각 finding은 관련 ID와 서로 다른 두 구현이 가능해지는 구체적 반례를 가진다. 암묵적 assumption·모호한 문구의 탐지는 단어 정규식이 아니라 이 auditor의 의미 검사가 담당한다 — 정규식은 정직한 문서만 잡고 부정직한 문서를 놓친다. 하나라도 있으면 C 또는 O로 승격하고 `resolve_findings` 또는 `ask_choices`로 돌아간다. auditor PASS는 미래의 모든 선택을 수학적으로 증명하지 않는다.

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

proof 하나라도 빠지거나 satisfied가 false면 material choice 후보로 승격한다. unknown reference, plural `unit_ids` 누락, incomplete full coverage도 FAIL이다. cold finding이 confirmed C를 다시 열면 그 C를 `reask`로 되돌리고 `SAME` 재확정 또는 supersession으로만 닫는다.

## Response-log-bound confirmations

사용자 확정의 유일한 증거는 사용자가 직접 실행한 `record_response.py`의 hash-chained 로그다. validator는 confirmed/superseded/reask C의 `user_response`, supersession, 두 confirmation 각각에 대해 `response_ref`의 hash 일치, `confirmed_at == entry.at`, exact 텍스트의 NFC 동일성, `C<n>=<답>` 문법(confirmation은 `CONFIRM ALIGNMENT:` / `CONFIRM HANDOFF:` prefix)을 검사한다. 로그 chain이 깨지면 문서 전체가 실패한다. 이 결속은 위조 불가가 아니라 위조 흔적 보장이다: LLM이 로그를 대신 쓰는 것은 막을 수 없지만, 그 행위는 세션 transcript에 도구 호출로 남는다.

## Digest-bound reviews and confirmations

정규화된 spec_projection의 sha256과 repository_context object의 sha256을 모든 receipt에 저장한다. RFC3339 timestamp가 서로 다른 offset을 사용해도 같은 instant로 비교한다. 어느 digest든 현재 값과 다르면 receipt는 stale이고 해당 review를 다시 실행한다. C의 affected_spec_ids, affected_acceptance_ids, affected_unit_ids는 계산된 reverse 목록과 정확히 일치해야 한다. choice 변경은 그 reverse 목록의 S/A/U와 관련 receipt를 stale로 만들고, stale receipt는 gate의 fresh review를 충족하지 못한다. receipt timestamp만 바뀌면 review freshness는 유지되며, review output 변경은 confirmation만 stale로 만든다.

gate 실행 시 validator는 `git_head`/`file` repository context entry를 실제 저장소에서 재관찰한다. drift, 재관찰 불능, observable(git_head/file) entry가 하나도 없는 context는 gate 오류이고 `next_action: research_facts`로 되돌린다 — command/runtime만으로 재관찰을 회피할 수 없다. `command|runtime` entry는 재관찰 불가로 `unobserved_context`에 보고한다. `--repo-root`로 저장소를 지정하고, cross-machine 리뷰에서만 `--no-observe`로 생략한다. 생략 여부는 출력의 `observation` 필드에 남는다: gate/claimed 실행에서 `enabled`(재관찰함) 또는 `skipped`(--no-observe), gate가 아닌 structural 실행에서 `not-required`.

receipt의 `ambiguity_receipt_digest`/`cold_receipt_digest`는 receipt 전체(generated_at 포함)를 hash하므로, receipt의 generated_at만 바뀌어도 그 receipt에 결속된 confirmation은 stale이 되어 재확인이 필요하다. 이는 보수적(fail-closed) 설계다 — receipt를 다시 생성했다는 것은 review를 다시 돌렸다는 뜻이기 때문이다. review의 spec/repository binding freshness(`spec_digest`/`repository_context_digest`)는 이와 별개로 계산한다.

alignment summary confirmation은 다음 shape다.

```json
{
  "confirmation_id": "UC1",
  "exact_response": "CONFIRM ALIGNMENT: 요약이 내 답을 정확히 반영한다",
  "response_ref": {"seq": 9, "hash": "sha256:..."},
  "confirmed_at": "2026-08-31T12:00:00+09:00",
  "spec_digest": "sha256:...",
  "repository_context_digest": "sha256:...",
  "ambiguity_review_id": "R1",
  "ambiguity_receipt_digest": "sha256:..."
}
```

handoff document confirmation은 위 필드에 `cold_review_id`, `cold_receipt_digest`를 추가한다. 두 confirmation ID는 달라야 하며 handoff confirmation은 alignment confirmation보다 나중 seq·나중 confirmed_at이고 cold receipt의 generated_at 이후에 생성돼야 한다. confirmations는 top-level spec projection에 포함하지 않는다.

## Gates and computed next_action

`aligned`는 모든 C가 log-bound confirmed 또는 valid superseded이고(reask 0), open O가 0이고, 12 surface가 current confirmed C 또는 immutable F로 닫히고, repository drift가 없고, fresh ambiguity PASS와 log-bound alignment summary confirmation이 있을 때만 가능하다. `handoff_ready`는 여기에 implementation target, session complete, S provenance·S-A-U mapping 완전, U cycle/orphan 0, placeholder·open O 0, fresh cold PASS, cold 이후 fresh handoff confirmation을 추가로 요구한다. planning state이며 실행 권한이 아니다.

frontmatter의 `alignment_status`/`handoff_status`는 validator가 계산한다. substance가 충족됐는데 flag가 낮으면 `next_action: stamp_status`이고 `--stamp`가 frontmatter를 갱신한다. substance보다 높은 주장은 오류다. validator는 문서에 next_action을 저장하지 않는다. parse 가능한 문서에서 session_status가 paused면 `pause`를 반환한다. 그 외 첫 조건 하나만 반환한다.

1. repository evidence/facts missing/unusable, context drift, open research O → `research_facts`
2. open external_dependency O → `pause`
3. surface missing/unclassified/invalid resolution, 또는 candidate/asked C가 지배하는 surface(uncovered) → `map_choices`
4. reask/incomplete C 또는 open choice O → `ask_choices` (candidate/asked C는 3에서 이미 uncovered로 잡히므로 map_choices가 먼저 반환된다)
5. S/A/U trace, mapping, graph incomplete → `compile_spec`
6. planner placeholder → `resolve_findings`
7. ambiguity receipt missing/stale → `run_ambiguity_audit`
8. ambiguity findings 또는 conflict O → `resolve_findings`
9. alignment confirmation missing/stale → `request_final_confirmation`
10. decision target: substance 충족 + flag 미달 → `stamp_status`; gate 충족 → `complete`
11. implementation cold receipt missing/stale → `run_cold_consumer`
12. cold blocker/incomplete local proof → `resolve_findings`
13. handoff confirmation missing/stale → `request_final_confirmation`
14. substance 충족 + flag 미달 → `stamp_status`; all gates satisfied → `complete`

허용 vocabulary는 `research_facts`, `map_choices`, `ask_choices`, `compile_spec`, `run_ambiguity_audit`, `run_cold_consumer`, `resolve_findings`, `request_final_confirmation`, `stamp_status`, `complete`, `pause`다. 총 라운드 제한은 없고 dependency 없는 질문은 라운드당 최대 8개, 4라운드마다 checkpoint다. complete는 gate 충족 때만 가능하며 스스로 임의 종료하지 않는다. 구현 중 새 material choice가 나오면 구현을 중단하고 새 C로 되돌린다.

## Deterministic validator semantics

validator는 UTF-8/usage 실패와 missing sibling script(record_response.py)·비정규 파일 response_log을 exit 2로, validation failure를 exit 1로, pass를 exit 0으로 반환한다. 정확한 frontmatter 10 key와 type/enum/RFC3339, safe relative `response_log`, git_head/file locator shape, canonical fence 1개를 검사하고, duplicate-key detecting JSON loader로 duplicate key와 NaN/Infinity를 거부한다. exact top-level/entry key·type, frontmatter/contract target·revision, register prefix와 global ID uniqueness를 검사한다. C state/null 규칙, alternatives/value/origin, 확정 문법과 response-log binding(SAME은 선행 명시답과 같은 alternative만 재확정), policy/supersession/cascade/reask, question round/checkpoint와 dependency를 검사한다. 위임·자유 문장은 별도 denylist가 아니라 `C<n>=<답>` 문법과 alternative 일치로 걸러진다.

validator는 exact 12 DS name과 resolution, S provenance, S-A-U mapping과 reverse affected lists, U DAG/order/cycle/orphan, O 상태를 계산한다. computed digest, stale receipt/confirmation, review output과 full coverage, gate 시 repository 재관찰(observable entry floor 포함)도 검사한다. frontmatter가 aligned 또는 ready를 주장하면 CLI가 structural이어도 해당 gate를 강제한다. RFC3339 소수부는 6자리로 정규화해 Python 3.9–3.14에서 동일하게 파싱한다. placeholder 검사는 예약 sentinel(`{{TODO …}}`류 double-brace, `[TODO]`류 bracket)만 잡고 code span을 stripping하지 않으며 planner-authored text에만 적용한다 — `Result<T, E>`·`{{username}}`·"create a TODO item"은 오탐하지 않고, 의미적 미완성·assumption은 auditor/cold consumer의 finding이 잡는다.

JSON 출력에는 `substance`(계산된 aligned/handoff_ready), `observation`(enabled/skipped/not-required), `context_drift`, `unobserved_context`, `response_log`, `stamped`가 포함된다. `structural`은 shape/type/ID/reference/digest/binding을 검사하고 candidate/asked/reask C, open O, missing receipt, finding receipt를 허용한다. `aligned`와 `handoff-ready`는 위 gate 정의를 강제한다. alignment confirmation만으로 handoff-ready가 되지 않으며 cold 이후 별도 handoff confirmation이 필요하다.
