# Canonical contract schema

`json align-goal-contract` block의 exact snake_case shape다. 모든 object는 아래에 명시된 key만 허용한다. alias, top-level `next_action`, top-level `spec_digest`, top-level `repository_context_digest`는 거부한다. 문서에는 이 fence가 정확히 하나만 있어야 하며, summary·PRD·PRFAQ는 projection이다.

## Frontmatter and response log

goal artifact frontmatter는 정확히 다음 10개 key만 가진다: `schema`, `title`, `target`, `session_status`, `alignment_status`, `handoff_status`, `revision`, `created`, `updated`, `response_log`. schema는 `align-goal/v1`, session_status는 `active|waiting|paused|complete`, alignment_status는 `exploring|aligned|rejected`, handoff_status는 `not_requested|draft|ready`다. target이 `decision`이면 handoff_status는 `not_requested`여야 한다. created/updated/captured_at과 확인 시각은 RFC3339 형식이다. `alignment_status`/`handoff_status`는 validator가 계산해 `--stamp`로 기록하는 값이며, substance보다 앞선 주장은 오류다.

`response_log`는 goal 문서 디렉터리 기준의 safe relative path다(절대 경로·`..`·`\` 금지). 사용자가 `record_response.py`로 직접 기록한 JSONL이며 각 항목은 정확히 다음 shape다.

```json
{"seq": 1, "at": "2026-08-31T12:00:00+09:00", "text": "C1=ALT2", "prev": null, "hash": "sha256:..."}
```

`seq`는 1부터 연속, `prev`는 직전 항목의 hash(첫 항목은 null), `at`은 비감소, `hash`는 `{seq, at, text, prev}`의 canonical JSON sha256이다. chain이 깨지면 문서 전체가 validation failure다. `text`는 `;`로 구분된 확정 segment들 또는 자유 문장(supersession·confirmation 전문)이다.

## Exact top-level

```json
{
  "contract_version": "align-goal/v1",
  "revision": 1,
  "target": "decision",
  "goal": {"statement": "...", "success": ["..."], "failure": ["..."], "non_goals": ["..."]},
  "repository_context": {"root": "...", "captured_at": "2026-08-31T12:00:00+09:00", "entries": [{"kind": "git_head", "locator": "HEAD", "digest": "sha256:..."}]},
  "facts": [],
  "choices": [],
  "question_rounds": [],
  "decision_surfaces": [],
  "specifications": [],
  "acceptance_checks": [],
  "implementation_units": [],
  "open_items": [],
  "reviews": {"ambiguity_auditor": null, "cold_consumer": null},
  "confirmations": {"alignment_summary": null, "handoff_document": null}
}
```

`contract_version`는 `align-goal/v1`, `target`는 `decision|implementation`, `revision`은 1 이상의 integer다. contract target/revision은 frontmatter와 같아야 한다. `repository_context.entries`는 각기 `kind`, `locator`, `digest`만 가지며 kind는 정확히 `git_head|file|command|runtime` 중 하나다. `git_head`의 locator는 `HEAD` 또는 full commit hash이고 digest는 resolve된 commit id(ascii lowercase)의 sha256이다. `file`의 locator는 repo root 기준 safe relative path이고 digest는 파일 바이트의 sha256이다. gate 실행 시 validator가 이 두 kind를 실제 저장소에서 재관찰해 drift를 차단하며, `command|runtime`은 재관찰 불가로 보고만 한다. 이는 F.sources의 kind인 `path|url|command|runtime`, value 필드와 별도 namespace다.

## F: observed fact

```json
{
  "id": "F1",
  "observation": "해석 없이 exact하게 관찰한 사실",
  "sources": [{"kind": "path", "value": "src/a.py:10", "digest": "sha256:..."}],
  "observed_at": "2026-08-31T12:00:00+09:00",
  "stability": "snapshot",
  "stability_basis": null,
  "limits": "이 사실이 보장하지 않는 범위"
}
```

source kind는 `path|url|command|runtime`, stability는 `snapshot|immutable_for_scope`다. `immutable_for_scope`는 nonempty stability_basis가 필요하고 forced consequence의 F 근거는 이것만 가능하다. source digest가 null이면 limits에 그 한계를 적는다.

## C: material choice

```json
{
  "id": "C1",
  "question": "어떤 exact 구현 결과를 선택합니까?",
  "alternatives": [{"id": "ALT1", "value": "정확한 값", "outcome_delta": "결과 차이", "origin": "llm"}, {"id": "ALT2", "value": "다른 정확한 값", "outcome_delta": "결과 차이", "origin": "llm"}],
  "recommendation": {"alternative_id": "ALT1", "rationale": "추천 이유", "evidence_fact_ids": ["F1"]},
  "depends_on_choice_ids": [],
  "choice_kind": "discrete",
  "policy_targets": [],
  "user_response": null,
  "confirmed_alternative_id": null,
  "confirmed_value": null,
  "scope": ["적용 범위"],
  "consequences": ["선택 결과"],
  "affected_spec_ids": [],
  "affected_acceptance_ids": [],
  "affected_unit_ids": [],
  "status": "candidate",
  "reask_reason": null,
  "supersession": null
}
```

alternative의 `origin`은 `llm|user`다. 사용자가 목록 밖 값을 `C1=OTHER: <값>`으로 답하면 그 값을 가진 `origin: user` alternative를 추가해 확정한다. `choice_kind`는 `discrete|policy`다. discrete는 policy_targets가 빈 배열이고 policy는 exact nonempty policy_targets를 가진다. status는 `candidate|asked|confirmed|superseded|reask`다. candidate/asked는 user_response, confirmed alternative/value, reask_reason, supersession이 모두 null이다.

confirmed의 `user_response`는 정확히 다음 shape이고, `confirmed_value`는 선택한 alternative.value와 정확히 같아야 한다.

```json
{"exact": "C1=ALT1", "response_ref": {"seq": 1, "hash": "sha256:..."}, "confirmed_at": "2026-08-31T12:00:00+09:00"}
```

`response_ref`는 response log 항목을 가리킨다. validator는 hash 일치, `confirmed_at == entry.at`, `exact`가 그 항목의 전문 또는 `;` segment와 NFC 동일함, segment가 `C<n>=<답>` 문법으로 이 C를 지목함, `<답>`이 확정 alternative의 ID 또는 value와 정확히 일치함(`OTHER:`는 origin user, `SAME`은 이전 명시 답 필요)을 모두 검사한다. recommendation만으로 confirmed할 수 없고 자유 문장은 문법에 걸린다.

`reask`는 review finding이 confirmed C를 다시 연 전이 상태다: 기존 user_response/confirmed 값을 보존하고 nonempty `reask_reason`을 기록하며, gate를 unresolved로 차단한다. `SAME` 재확정만 reask를 닫는다 — 값을 바꾸려면 supersession으로 기록한다.

superseded는 원래 user_response를 보존하고 다음 supersession을 추가한다.

```json
{"exact_user_response": "C1 supersedes to the new direction because of C2", "response_ref": {"seq": 4, "hash": "sha256:..."}, "confirmed_at": "...", "basis_choice_ids": ["C2"], "basis_fact_ids": [], "derivation": "C2 때문에 C1 범위가 소멸한다."}
```

`exact_user_response`는 로그 항목 전문과 NFC 동일해야 하고 항목 text가 해당 C ID를 지명해야 한다. basis에는 confirmed C 또는 immutable F가 하나 이상 있어야 한다. superseded C는 current DS/S provenance나 forced basis로 사용할 수 없다. **cascade**: supersede된 C에 의존하던 confirmed C는 supersession의 seq 이후 항목으로 재확정되어 있거나 `reask`/`superseded`여야 한다.

`scope`와 `consequences`는 required nonempty unique strings이고, `policy_targets`도 unique strings 배열이어야 하며 policy choice에서는 nonempty, discrete choice에서는 empty다. affected S/A/U 목록은 계산된 reverse 목록과 정확히 일치해야 한다.

## Question round

```json
{
  "number": 4,
  "choice_ids": ["C7", "C8"],
  "asked_at": "2026-08-31T12:00:00+09:00",
  "checkpoint": {"confirmed_choice_ids": ["C1"], "unresolved_choice_ids": ["C8"], "affected_spec_ids": ["S1"], "next_question_choice_ids": ["C9"], "recorded_at": "2026-08-31T12:00:00+09:00"}
}
```

round choice_ids는 unique 1..8개다. candidate를 제외한 asked/confirmed/superseded/reask C는 정확히 한 round에 속하고(reask는 원래 round를 유지한다), dependency C는 더 이른 round에서 답변된 choice여야 한다. number가 4의 배수면 complete checkpoint가 필수이고, 그 외 round는 checkpoint가 반드시 null이어야 한다(비-4 배수 round의 비-null checkpoint는 validation failure다).

## DS: exact 12 surfaces

각 surface는 아래 exact shape를 가진다. names는 [decision-surfaces.md](decision-surfaces.md)의 12개만 허용한다.

```json
{
  "id": "DS1",
  "name": "goal_success_failure_non_goal",
  "classification": "applicable",
  "resolution": {"mode": "choice", "choice_ids": ["C1"], "fact_ids": [], "derivation": null},
  "reason": "적용 또는 비적용의 구체적 근거"
}
```

classification은 `applicable|not_applicable`, resolution.mode는 `choice|forced`다. choice mode는 C nonempty, F empty, derivation null이다. candidate/asked governing C가 있는 surface는 exploration 중 shape-valid이지만 aligned 전에는 uncovered로 계산하고, reask governing C는 unresolved로 gate를 막는다. forced mode는 confirmed C 또는 immutable F가 하나 이상이고 exact derivation이 필수다. not_applicable도 같은 resolution 규칙을 사용하며 관례만으로 닫을 수 없다. aligned에서는 governing C가 모두 현재 confirmed여야 하고 superseded C를 사용할 수 없다.

## S: specification

```json
{
  "id": "S1",
  "kind": "behavior",
  "statement": "exact 구현 계약",
  "provenance": {"mode": "choice", "choice_ids": ["C1"], "fact_ids": [], "derivation": null}
}
```

kind는 `behavior|error|name|format|contract|data|state|structure|dependency|compatibility|security|performance|operation|verification`이다. 모든 kind에 같은 provenance 규칙을 적용하며 verification 예외는 없다. choice mode의 C는 confirmed여야 하고(전이 중인 reask는 구조 오류 없이 untraced로 gate만 차단), `derivation`은 null로 고정한다. forced mode는 confirmed C 또는 immutable F와 nonempty derivation을 요구한다.

**Placeholder sentinel.** planner-authored 텍스트의 미완성 슬롯은 예약 sentinel로만 표시한다: `{{TODO …}}`, `{{TBD …}}`, `{{FIXME …}}`, `{{FILL …}}`, `{{DECIDE …}}`, `{{PLACEHOLDER …}}`, `{{결정 …}}`(키워드로 시작하는 double-brace, `{{DECIDE_LATER}}`처럼 구분자 뒤 임의 텍스트 허용) 또는 `[TODO]`류 bracket. validator는 이 sentinel을 backtick code span 안이든 밖이든 동일하게 차단한다. `{{username}}` 같은 일반 템플릿 토큰, `Result<T, E>` 같은 코드 표기, "create a TODO item" 같은 산문은 sentinel이 아니므로 통과한다. sentinel을 쓰지 않은 실질적 미완성은 이 lint가 아니라 cold consumer의 `underspecified_clauses`가 잡는다.

## A: acceptance check

```json
{
  "id": "A1",
  "spec_ids": ["S1"],
  "setup": "초기 환경과 상태",
  "input": "입력",
  "action": "행동",
  "observable_or_inspection": "관찰 또는 검사 결과",
  "pass_condition": "exact 통과 조건",
  "evidence": "남길 증거",
  "acceptance_type": "functional",
  "measurement": null
}
```

acceptance_type은 `functional|non_functional`이다. non_functional이면 measurement의 `metric`, `threshold`, `conditions`, `method`가 모두 필요하다.

## U: implementation unit

```json
{
  "id": "U1",
  "title": "독립적으로 관찰·검증 가능한 변화",
  "spec_ids": ["S1"],
  "acceptance_ids": ["A1"],
  "inputs": ["입력"],
  "outputs": ["출력"],
  "change_boundary": ["파일·symbol·경계"],
  "forbidden_changes": ["금지 변경"],
  "dependency_unit_ids": [],
  "execution_order": 1,
  "completion_evidence": ["검증 명령과 산출물"]
}
```

decision target의 U는 빈 배열이어야 한다. dependency order는 현재 unit보다 작아야 하며 self/unknown/duplicate edge와 cycle을 거부한다. S/A/U mapping과 reverse mapping이 완전해야 한다. orphan은 S/A 없는 U, 어떤 U에도 매핑되지 않은 S/A, unknown reference/dependency다. C.affected_spec_ids, C.affected_acceptance_ids, C.affected_unit_ids는 계산된 reverse 목록과 정확히 일치해야 한다.

## O: open item

```json
{
  "id": "O1",
  "kind": "research",
  "description": "미확정 선택, 충돌, 조사 또는 외부 의존성",
  "blocking_ids": ["S1"],
  "status": "open",
  "resolution": null
}
```

kind는 `choice|conflict|research|external_dependency`, status는 `open|resolved`다. resolved이면 resolution의 `fact_ids`, `choice_ids`, `note`가 필요하다. gate는 open O만 차단한다.

resolved 예시는 다음과 같다.

```json
{"fact_ids": ["F2"], "choice_ids": [], "note": "조사 결과로 해결"}
```

## Reviews, confirmations, and projection

Ambiguity receipt:

```json
{"review_id": "R1", "reviewer": "ambiguity_auditor", "status": "pass", "spec_digest": "sha256:...", "repository_context_digest": "sha256:...", "generated_at": "2026-08-31T12:00:00+09:00", "output": {"new_material_choices": [], "counterexamples": [], "contradictions": [], "invalid_forced_consequences": [], "invalid_local_coding": [], "unexamined_surfaces": []}}
```

Cold receipt:

```json
{"review_id": "R2", "reviewer": "cold_consumer", "status": "pass", "spec_digest": "sha256:...", "repository_context_digest": "sha256:...", "generated_at": "2026-08-31T12:00:00+09:00", "output": {"steps": [{"step": "...", "spec_ids": ["S1"], "acceptance_ids": ["A1"], "unit_ids": ["U1"]}], "required_user_choices": [], "implicit_assumptions": [], "contradictions": [], "underspecified_clauses": [], "unmapped_spec_ids": [], "local_choices": []}}
```

두 receipt의 output key와 local proof는 [review-protocol.md](review-protocol.md)에 고정한다. confirmations는 `alignment_summary`와 `handoff_document` 두 개이며, 각각 `exact_response`, `response_ref`, `confirmed_at`, `spec_digest`, `repository_context_digest`를 보존한다. 로그 항목은 각각 `CONFIRM ALIGNMENT:` / `CONFIRM HANDOFF:`로 시작하는 전문이어야 하고 exact_response와 NFC 동일해야 한다. handoff confirmation은 alignment confirmation보다 나중 seq·나중 시각이고 cold receipt의 generated_at 이후여야 하며 둘의 ID가 달라야 한다.

`spec_projection`은 `contract_version`, `revision`, `target`, `goal`, `facts`, `choices`, `question_rounds`, `decision_surfaces`, `specifications`, `acceptance_checks`, `implementation_units`, `open_items`만 포함한다. 이 projection을 canonical JSON으로 정규화해 spec_digest를 계산한다. repository_context_digest는 repository_context object만 hash한다. reviews와 confirmations는 두 projection에서 제외한다.

정규화는 모든 문자열을 NFC로 정규화한 뒤 `json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")`이며 digest는 `sha256:` + lowercase 64 hex다. response log의 chain hash도 같은 canonicalization을 사용한다. receipt는 computed digest를 저장하고 자기 자신을 hash하지 않는다. review output 변경은 confirmation만 stale로 만들고, spec/repository 변경은 관련 receipt와 confirmation을 stale로 만든다.
