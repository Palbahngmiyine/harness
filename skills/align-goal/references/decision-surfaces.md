# Decision Surface Coverage

매 세션에서 정확히 아래 12개를 한 번씩 검사한다. name, id, classification, resolution, reason을 저장한다. `resolution.mode=choice`면 C만, `forced`면 confirmed C 또는 immutable_for_scope F와 exact derivation만 허용한다. not_applicable도 동일한 resolution 규칙을 사용한다.

1. `goal_success_failure_non_goal` — 목표, 성공, 실패, non-goal, 우선순위와 범위
2. `user_behavior_defaults_order_atomicity_idempotency` — 사용자 행동, default, 순서, atomicity, idempotency
3. `errors_partial_failure_recovery_rollback` — 오류, 부분 실패, recovery, rollback, 재시도 후 상태
4. `commands_flags_routes_events_config_types_fields_paths_formats` — command, flag, route, event, config/env key, type, field, path, format
5. `data_state_ownership_lifecycle_persistence` — data/state ownership, lifecycle, persistence, 삭제와 보존
6. `api_event_file_internal_contract_versioning` — API, event, file, internal contract, schema와 versioning
7. `architecture_modules_components_dependencies_stack` — architecture, module/component 경계, dependency, 기술 stack
8. `concurrency_timing_resource_policy` — concurrency, timing, timeout, ordering, resource policy와 한도
9. `compatibility_migration_rollout` — compatibility, migration, rollout, downgrade와 기존 사용자 영향
10. `security_privacy_authorization_destructive_side_effect` — security, privacy, authorization, secret 처리, destructive side effect
11. `performance_observability_operation` — performance 수치, 관측성, log/metric/trace, operation과 대응
12. `verification_acceptance` — verification, acceptance setup/input/action/observable/pass/evidence

## Mapping procedure

repository와 runtime에서 해당 표면의 존재를 F로 확인한다. 둘 이상의 구현이 결과를 다르게 만들면 exact alternatives를 가진 C로 질문한다. recommendation과 repository convention은 evidence일 뿐 확정이 아니다. immutable fact 또는 confirmed choice가 결과를 하나로 강제할 때만 forced resolution과 derivation을 사용한다. choice mode에서 governing C는 current confirmed여야 하며 superseded C는 aligned의 근거가 될 수 없다.

반복 항목을 policy C 하나로 묶는 것은 질문·대안·결과가 동일할 때뿐이다. 모든 적용 대상을 C.policy_targets와 C.scope에 열거한다. applicable surface의 choice resolution에는 C가 비어 있으면 안 된다. not_applicable은 구체적인 reason과 F를 가지며, 강제가 아니면 not_applicable 판단 자체를 사용자 choice로 만든다.

## Classification boundary

local coding은 다음을 모두 증명할 때만 허용한다: observable behavior와 테스트 결과 동일, 명세에 등장하는 identifier·cross-file symbol·path·format·schema·persisted field 불변, dependency·data·concurrency·security·performance·compatibility·build/deploy 영향 없음, 하나의 private unit 내부, 변경해도 다른 spec·acceptance 불변. 따라서 private helper inline/split, formatting, private local variable 이름만 대표 사례다. public/cross-file identifier, route, flag, JSON field, DB column, file layout, error format, retry policy, module boundary는 material choice다. NFR은 수치·측정 조건·방법이 없으면 DS11 choice로 되돌린다.
