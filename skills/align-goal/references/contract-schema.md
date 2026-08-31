# Canonical contract schema

`json align-goal-contract` block의 exact snake_case shape다. 모든 object는 아래에 명시된 key만 허용한다. alias, top-level `next_action`, top-level `spec_digest`, top-level `repository_context_digest`는 거부한다. 문서에는 이 fence가 정확히 하나만 있어야 하며, summary·PRD·PRFAQ는 projection이다.

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

`contract_version`는 `align-goal/v1`, `target`는 `decision|implementation`, `revision`은 1 이상의 integer다. contract target/revision은 frontmatter와 같아야 한다. `repository_context.entries`는 각기 `kind`, `locator`, `digest`만 가지며 kind는 정확히 `git_head|file|command|runtime` 중 하나다. `root`, `captured_at`, entries가 필수다. 이는 F.sources의 kind인 `path|url|command|runtime`, value 필드와 별도 namespace다.

goal artifact frontmatter는 정확히 다음 9개 key만 가진다: `schema`, `title`, `target`, `session_status`, `alignment_status`, `handoff_status`, `revision`, `created`, `updated`. schema는 `align-goal/v1`, session_status는 `active|waiting|paused|complete`, alignment_status는 `exploring|aligned|rejected`, handoff_status는 `not_requested|draft|ready`다. target이 `decision`이면 handoff_status는 `not_requested`여야 한다. created/updated/captured_at과 확인 시각은 RFC3339 형식이어야 한다.

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
  "alternatives": [{"id": "ALT1", "value": "정확한 값", "outcome_delta": "결과 차이"}, {"id": "ALT2", "value": "다른 정확한 값", "outcome_delta": "결과 차이"}],
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
  "supersession": null
}
```

`choice_kind`는 `discrete|policy`다. discrete는 policy_targets가 빈 배열이고 policy는 exact nonempty policy_targets를 가진다. candidate/asked는 user_response, confirmed alternative/value, supersession이 모두 null이다. confirmed는 다음을 모두 요구하며 confirmed_value는 선택한 alternative.value와 정확히 같아야 한다.

```json
{"exact": "C1=ALT1 exact value", "turn_id": "turn-123", "confirmed_at": "2026-08-31T12:00:00+09:00"}
```

turn_id 또는 confirmed_at 중 하나 이상이 필요하다. recommendation만으로 confirmed할 수 없고 vague phrase는 exact/value 어디에도 넣지 않는다. superseded는 원래 confirmation을 보존하고 다음 supersession을 요구한다.

```json
{"exact_user_response": "C1은 C2 때문에 폐기한다", "turn_id": "turn-456", "confirmed_at": "...", "basis_choice_ids": ["C2"], "basis_fact_ids": [], "derivation": "C2 때문에 C1 범위가 소멸한다."}
```

superseded C는 원래 user_response, confirmed_alternative_id, confirmed_value를 보존하고 supersession을 추가한다. 보존된 original user_response도 confirmed와 동일하게 exact text와 turn_id 또는 confirmed_at을 검증한다. superseded C는 current DS/S provenance나 forced basis로 사용할 수 없다. supersession basis에는 confirmed C 또는 immutable F가 하나 이상 있어야 한다. status는 `candidate|asked|confirmed|superseded`다. `scope`와 `consequences`는 required nonempty unique strings이고, `policy_targets`도 unique strings 배열이어야 하며 policy choice에서는 nonempty, discrete choice에서는 empty다. affected S/A/U 목록은 계산된 정확한 범위를 기록한다.

## Question round

```json
{
  "number": 4,
  "choice_ids": ["C7", "C8"],
  "asked_at": "2026-08-31T12:00:00+09:00",
  "checkpoint": {"confirmed_choice_ids": ["C1"], "unresolved_choice_ids": ["C8"], "affected_spec_ids": ["S1"], "next_question_choice_ids": ["C9"], "recorded_at": "2026-08-31T12:00:00+09:00"}
}
```

round choice_ids는 unique 1..8개다. candidate를 제외한 asked/confirmed/superseded C는 정확히 한 round에 속하고, dependency C는 더 이른 round에서 confirmed여야 한다. number가 4의 배수면 complete checkpoint가 필수이고 그 외에는 checkpoint null을 허용한다.

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

classification은 `applicable|not_applicable`, resolution.mode는 `choice|forced`다. choice mode는 C nonempty, F empty, derivation null이다. candidate/asked governing C가 있는 surface는 exploration 중 shape-valid이지만 aligned 전에는 uncovered로 계산한다. forced mode는 confirmed C 또는 immutable F가 하나 이상이고 exact derivation이 필수다. not_applicable도 같은 resolution 규칙을 사용하며 관례만으로 닫을 수 없다. aligned에서는 governing C가 모두 현재 confirmed여야 하고 superseded C를 사용할 수 없다.

## S: specification

```json
{
  "id": "S1",
  "kind": "behavior",
  "statement": "exact 구현 계약",
  "provenance": {"mode": "choice", "choice_ids": ["C1"], "fact_ids": [], "derivation": null}
}
```

kind는 `behavior|error|name|format|contract|data|state|structure|dependency|compatibility|security|performance|operation|verification`이다. 모든 kind에 같은 provenance 규칙을 적용하며 verification 예외는 없다. choice mode는 confirmed C만, `derivation`은 null로 고정한다. forced mode는 confirmed C 또는 immutable F와 nonempty derivation을 요구한다.

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

두 receipt의 output key와 local proof는 [review-protocol.md](review-protocol.md)에 고정한다. confirmations는 `alignment_summary`와 `handoff_document` 두 개이며, 각각 exact_response, turn_id 또는 confirmed_at, spec_digest, repository_context_digest를 보존한다. handoff confirmation은 alignment confirmation의 confirmed_at 이후이고 cold receipt의 generated_at 이후에 생성돼야 하며 둘의 ID가 달라야 한다.

`spec_projection`은 `contract_version`, `revision`, `target`, `goal`, `facts`, `choices`, `question_rounds`, `decision_surfaces`, `specifications`, `acceptance_checks`, `implementation_units`, `open_items`만 포함한다. 이 projection을 canonical JSON으로 정규화해 spec_digest를 계산한다. repository_context_digest는 repository_context object만 hash한다. reviews와 confirmations는 두 projection에서 제외한다.

정규화는 `json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")`이며 digest는 `sha256:` + lowercase 64 hex다. receipt는 computed digest를 저장하고 자기 자신을 hash하지 않는다. review output 변경은 confirmation만 stale로 만들고, spec/repository 변경은 관련 receipt와 confirmation을 stale로 만든다.
