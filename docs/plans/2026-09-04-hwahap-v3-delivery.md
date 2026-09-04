# Hwahap V3 구현·검증 계획

- 상위 기획: [2026-09-04-hwahap-v3.md](2026-09-04-hwahap-v3.md)
- 상태: 제안
- 원칙: 기획 계약을 먼저 고정하고 runtime은 작은 vertical slice로 검증한다.

## 1. 전달 전략

V3는 big-bang replacement로 구현하지 않는다. v2를 유지한 상태에서 `hwahap/v3` contract와 Rust runtime을 병렬로 추가하고, Desktop smoke와 end-to-end parity를 통과한 뒤 기본 경로를 전환한다.

```text
P0 facts
  -> V3 contract
  -> Desktop/MCP shell
  -> ACP worker slice
  -> scheduler/state
  -> review/integration/PR
  -> adjust/ship
  -> migration
```

각 PR은 단독 rollback 가능해야 한다. red CI를 다음 PR에서 고친다는 계획은 허용하지 않는다.

## 2. PR sequence

### PR V3-0 — Compatibility probes

목적: architecture를 추정으로 잠그지 않는다.

산출물:

- Desktop MCP lifecycle probe
- Desktop sandbox/child process probe
- Rust ACP SDK -> pinned codex-acp handshake probe
- one-adapter multi-session/concurrency probe
- session config isolation probe
- ChatGPT auth path probe
- resume/cancel/process cleanup probe
- macOS/Windows evidence report

Acceptance:

- 각 probe는 command, environment, expected, observed, version, date를 기록
- 실패를 architecture decision으로 숨기지 않고 권장 topology 수정으로 연결
- credential contents를 artifact에 기록하지 않음
- process leak 0을 반복 실행에서 확인

### PR V3-1 — Contract and Plan Engine

목적: runtime 이전에 Blackbox-Zero planning contract를 고정한다.

산출물:

- `hwahap/v3` JSON schema
- Fact, Decision, Recommendation, Scenario, Acceptance, Unit, Test records
- `C<n>=REC`와 recommendation hash binding
- no-recommendation/probe-required states
- frontier derivation contract
- all-REC checkpoint
- deterministic `plan.md` renderer
- completeness/traceability validator
- v2 goal -> v3 planning import fixture

Acceptance:

- unanswered recommendation은 선택으로 간주되지 않음
- recommendation 수정 후 기존 `REC` answer가 stale 처리됨
- open decision/assumption/orphan mapping이 있으면 freeze 불가
- cold implementer finding을 숨기는 경로 없음
- property tests와 mutation tests가 negative cases를 고정

### PR V3-2 — Rust binary and Desktop surface

목적: 사용자가 Desktop에서 하나의 Hwahap capability로 사용한다.

산출물:

- `hwahap` Rust binary
- `hwahap mcp`, `doctor`, `verify`
- local Codex Skill
- MCP declaration/install flow
- tools: `plan`, `cycle`, `status`, `adjust`, `ship`
- durable run id and repository binding

Acceptance:

- idle 상시 daemon 없음
- Desktop에서 terminal 없이 plan 시작 가능
- low-level orchestration tools는 Parent Codex에 노출되지 않음
- same repo concurrent run policy가 deterministic
- binary/process/version readiness가 `doctor`에서 구분됨
- missing/unknown/installed를 혼동하지 않음

### PR V3-3 — ACP worker vertical slice

목적: `codex exec` 없이 unit 하나를 구현·검증한다.

산출물:

- official Rust ACP SDK v1 client
- pinned codex-acp resolver/install probe
- role-specific session profile
- model/mode/effort configuration
- permission handler
- ACP event reducer
- one worktree, one patch, one test receipt
- cancellation and teardown

Acceptance:

- nested `codex exec` 호출 0
- worker cwd는 unit worktree
- workspace-write 밖 변경 0
- network default deny
- Luna worker가 frozen unit을 구현
- command/file/usage events를 typed receipt로 환원
- process tree leak 0

### PR V3-4 — Scheduler and durable state

목적: 여러 unit을 LLM이 아닌 deterministic engine이 실행한다.

산출물:

- SQLite schema/migrations
- Run/Unit state machines
- DAG scheduler and bounded parallelism
- transition journal
- retry/review budget
- crash/restart resume
- cache key based on plan/unit/brief/input digest

Acceptance:

- cycle/DAG invalidity fail-closed
- dependency가 accepted 전 dependent 실행 불가
- crash injection 각 transition에서 duplicate side effect 없음
- accepted unchanged unit 재호출 0
- cancellation 후 child/session/worktree 상태 일관성 유지

### PR V3-5 — Model router

목적: cheap work는 Luna에 집중하고 escalation을 증거 기반으로 제한한다.

산출물:

- semantic model tiers
- risk scoring
- Luna/Terra/Sol role mapping
- runtime model availability validation
- escalation receipts
- role별 token/quota metrics

Acceptance:

- low-risk unit default Luna
- routine retry에 Sol 사용 금지
- unsupported model은 silent fallback하지 않음
- model change마다 reason 존재
- high-risk surface가 review 강화 없이 Luna-only로 끝나는 경로 없음
- model alias 변경이 contract schema를 바꾸지 않음

### PR V3-6 — Structured worker/reviewer control

목적: final-message 문자열 protocol을 제거한다.

산출물:

- worker result contract
- `PlanConflict` contract
- reviewer verdict/findings contract
- role별 최소 MCP/result surface
- invalid/missing structured result handling

Acceptance:

- `NEEDS_DECISION:` 첫 줄 parsing 없음
- `verdict: pass` 첫 줄 parsing 없음
- Worker가 parent/control-plane spawn tool에 접근하지 못함
- malformed result는 fail-closed
- PlanConflict가 code patch와 함께 성공 처리되지 않음

### PR V3-7 — Integration, final review, draft PR

목적: v2의 강한 delivery gate를 V3 runtime에 옮긴다.

산출물:

- topological patch integration
- full-suite
- scope/secret/freshness checks
- Sol final review
- report/summary
- draft PR creation

Acceptance:

- `git apply --check` 선행
- full-suite current integration diff에 결속
- final review가 current head/digest에 결속
- unplanned product decisions > 0이면 PR 성공 terminal 불가
- ready/merge/auto-merge 수행 안 함
- report conclusion/evidence/verification/limitations/usage 순서 고정

### PR V3-8 — Adjustment and Ship

목적: PR 확인 후 전체 cycle을 다시 돌리지 않고 조정한다.

산출물:

- feedback impact analysis
- affected decision/unit invalidation
- selective planning and `CONFIRM PLAN`
- selective rebuild/reintegration
- `SHIP` final gate
- draft -> ready transition

Acceptance:

- unaffected accepted unit 재실행 0
- material feedback을 local coding change로 축소할 수 없음
- ship 전 CI/head/final-review freshness 재검사
- merge/auto-merge 없음
- stale PR head에서 ship 거부

### PR V3-9 — Migration and default switch

목적: v2 사용자와 artifact를 안전하게 이동한다.

산출물:

- v2/v3 explicit selector during transition
- existing answers/facts/goal import policy
- no automatic trust of v2 build receipts
- install/update/uninstall flow
- Desktop compatibility matrix
- deprecation notice and rollback procedure

Acceptance:

- v2 run 중 V3 install이 기존 run을 손상하지 않음
- v3 failure 시 v2 skill로 되돌릴 수 있음
- global config를 덮어쓰지 않고 additive merge
- uninstall이 사용자 기존 MCP/Skill 설정을 보존
- default switch는 full E2E와 manual Desktop checklist 통과 뒤 수행

## 3. Test architecture

### 3.1 Deterministic unit tests

- contract/schema validation
- recommendation freshness/hash binding
- frontier and prerequisite graph
- traceability completeness
- state transition legality
- model routing and escalation
- DAG scheduling
- path/scope/secret policy
- report generation

### 3.2 Fake ACP harness

실제 모델 없이 다음 event를 결정적으로 생성한다.

- text/reasoning chunk
- shell command
- file change
- permission request
- usage
- malformed update
- disconnect/reconnect
- delayed completion
- cancellation race
- session load/resume

### 3.3 Live ACP smoke

실제 pinned codex-acp로 최소 fixture repository를 실행한다.

- Luna one-file change
- read-only reviewer
- concurrent independent sessions
- dependent units
- PlanConflict
- network denial
- cancellation
- app/adapter restart and resume

Live tests는 nightly/manual lane에 둘 수 있지만 release checklist에서는 필수다.

### 3.4 Desktop E2E

최소 matrix:

| OS | Path | Required scenarios |
|---|---|---|
| macOS current-1/current | ChatGPT Desktop Codex | install, plan, cycle, resume, PR, adjust, ship |
| Windows current-1/current | ChatGPT Desktop Codex | install, path quoting, process cleanup, resume |
| Linux | Codex CLI compatibility lane | core MCP/ACP/runtime regressions |

Desktop 내부 private endpoint는 테스트 대상이 아니다. 공개 Skill/MCP behavior만 검사한다.

### 3.5 Failure injection

- Hwahap process 종료
- codex-acp 종료
- Codex App Server 종료
- SQLite busy/corrupt copy
- disk full/permission denied
- worktree conflict
- patch apply conflict
- GitHub/gh failure
- CI pending/fail
- token/quota exhaustion
- user modifies PR head

각 case는 terminal state, resume action, retained evidence를 고정한다.

### 3.6 Coverage and mutation

- Rust line/branch coverage를 수치로 보고
- state transition, gate, permission, freshness 조건 mutation
- parser/schema fuzzing
- concurrency model testing 또는 loom 적용 가능성 평가
- process/resource leak repeat test
- formatter/clippy/deny/audit

수치 목표는 implementation PR에서 toolchain probe 후 고정하되, gate 조건의 mutation survival은 0을 목표로 한다.

## 4. Review gates

각 implementation PR은 다음 질문에 답해야 한다.

1. 이 변경이 Parent LLM에게 orchestration 결정을 다시 넘기는가?
2. 제품 결정을 hidden default로 만드는가?
3. Luna로 충분한 작업에 상위 모델을 사용하는가?
4. stronger model이 필요한 작업을 비용 이유로 Luna-only로 끝내는가?
5. sandbox/permission만 믿고 postcondition 검사를 제거하는가?
6. state를 resume했을 때 duplicate side effect가 가능한가?
7. current plan/current diff/current PR head에 evidence가 결속되는가?
8. Desktop 외 terminal 조작이 정상 UX에 필요한가?
9. 새 process/component 종류가 반드시 필요한가?
10. v2의 검증 불변식을 약화하는가?

한 항목이라도 설명되지 않으면 merge하지 않는다.

## 5. Release criteria

V3 default 전환 조건:

- P0 probe 완료와 문서화
- Plan completeness negative suite 통과
- recommendation freshness/property suite 통과
- Rust state/scheduler failure injection 통과
- nested `codex exec` 0 증명
- Luna-first routing receipts 확인
- macOS/Windows Desktop E2E 통과
- v2 parity fixture 통과
- 5개 이상의 실제 repository canary run
- canary run 모두 unplanned material decision 0
- orphan process 0
- draft PR -> adjustment -> ship end-to-end 통과
- rollback 절차 실제 확인

## 6. Current PR의 범위

이 문서와 상위 기획 PR은 설계 전용이다.

포함:

- V3 제품 계약
- lifecycle/architecture/model routing
- implementation PR sequence
- acceptance/test/release gates

미포함:

- v2 code 변경
- Rust runtime scaffold
- Codex/MCP 설정 변경
- model call
- global Hwahap 설치 변경
- branch protection 변경
