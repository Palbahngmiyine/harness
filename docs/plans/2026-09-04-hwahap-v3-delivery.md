# Hwahap V3 구현·검증 계획

- 상위 기획: [2026-09-04-hwahap-v3.md](2026-09-04-hwahap-v3.md)
- 상태: 제안
- 원칙: 기획 계약을 먼저 고정하고 runtime은 작은 vertical slice로 검증한 뒤, 최종 cutover에서 v2를 전면 제거한다.

## 1. 전달 전략

V3는 **breaking replacement**로 전달한다. v2와 v3를 사용자에게 동시에 제공하거나 migration compatibility layer를 유지하지 않는다. 다만 구현 품질을 위해 작업 자체는 작은 vertical slice로 나눈다.

권장 개발 방식은 V3 전용 integration branch에 V3-0~V3-8을 stacked/순차 검증하고, `main`에는 v2를 그대로 둔 뒤 마지막 V3-9 cutover에서 `skills/hwahap`을 V3로 전면 교체하는 것이다. 따라서 사용자가 보는 중간 dual-mode 상태는 만들지 않는다.

```text
P0 facts
  -> V3 contract
  -> Desktop/MCP shell
  -> ACP worker slice
  -> scheduler/state
  -> model routing
  -> structured review
  -> integration/PR
  -> adjust/ship
  -> BREAKING CUTOVER (remove v2, install V3)
```

각 구현 단계는 자체 테스트와 review를 통과해야 한다. red CI를 다음 단계에서 고친다는 계획은 허용하지 않는다. v2로 되돌아가기 위한 production compatibility code는 만들지 않는다. cutover 자체에 문제가 있으면 Git history에서 cutover PR/commit을 revert한다.

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

- 각 probe는 command, environment, expected, observed, version, date 기록
- 실패를 숨기지 않고 topology 수정으로 연결
- credential contents artifact 기록 금지
- 반복 실행 process leak 0

### PR V3-1 — Contract and Plan Engine

목적: runtime 이전에 Blackbox-Zero planning contract를 고정한다.

산출물:

- `hwahap/v3` JSON schema
- Fact, Decision, Recommendation, Scenario, Acceptance, Unit, Test records
- `C<n>=REC` + recommendation hash binding
- `no_recommendation` / `probe_required`
- frontier derivation contract
- all-REC checkpoint
- deterministic `plan.md` renderer
- completeness/traceability validator

Acceptance:

- unanswered recommendation을 선택으로 간주하지 않음
- recommendation 변경 후 기존 `REC` answer stale
- open decision/assumption/orphan mapping이 있으면 freeze 불가
- cold implementer finding을 숨기는 경로 없음
- property/mutation tests로 negative cases 고정
- v2 artifact import/compatibility code를 추가하지 않음

### PR V3-2 — Rust binary and Desktop surface

목적: 사용자가 Desktop에서 하나의 Hwahap capability로 사용한다.

산출물:

- `hwahap` Rust binary
- `hwahap mcp`, `doctor`, `verify`
- local Codex Skill
- MCP declaration/install flow
- tools: `plan`, `cycle`, `status`, `adjust`, `ship`
- durable run id와 repository binding

Acceptance:

- idle 상시 daemon 없음
- Desktop에서 terminal 없이 plan 시작 가능
- low-level orchestration tools Parent Codex 미노출
- same-repo concurrent run policy deterministic
- binary/process/version readiness를 installed/missing/unknown으로 구분

### PR V3-3 — ACP worker vertical slice

목적: `codex exec` 없이 unit 하나를 구현·검증한다.

산출물:

- official Rust ACP SDK v1 client
- pinned codex-acp resolver/install probe
- role-specific session profile
- model/mode/effort config
- permission handler
- ACP event reducer
- one worktree, one patch, one test receipt
- cancellation/teardown

Acceptance:

- nested `codex exec` 0
- worker cwd = unit worktree
- workspace-write 밖 변경 0
- network default deny
- Luna worker가 frozen unit 구현
- command/file/usage events typed receipt화
- process tree leak 0

### PR V3-4 — Scheduler and durable state

목적: 여러 unit을 LLM이 아닌 deterministic engine이 실행한다.

산출물:

- SQLite schema/migrations
- Run/Unit state machines
- DAG scheduler + bounded parallelism
- transition journal
- retry/review budget
- crash/restart resume
- plan/unit/input digest 기반 cache

Acceptance:

- invalid cycle/DAG fail-closed
- prerequisite accepted 전 dependent 실행 불가
- transition별 crash injection에서 duplicate side effect 없음
- unchanged accepted unit 재호출 0
- cancellation 후 child/session/worktree 일관성 유지

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
- routine retry에 Sol 금지
- unsupported model silent fallback 금지
- model change마다 reason 존재
- high-risk surface가 review 강화 없이 Luna-only로 끝나는 경로 없음

### PR V3-6 — Structured worker/reviewer control

목적: final-message 문자열 protocol을 제거한다.

산출물:

- worker result contract
- `PlanConflict` contract
- reviewer verdict/findings contract
- role별 최소 structured result/MCP surface
- invalid/missing result handling

Acceptance:

- `NEEDS_DECISION:` 첫 줄 parsing 없음
- `verdict: pass` 첫 줄 parsing 없음
- Worker가 parent/control-plane spawn tool에 접근하지 못함
- malformed result fail-closed
- PlanConflict + code patch를 successful result로 처리하지 않음

### PR V3-7 — Integration, final review, draft PR

목적: V3 native delivery gate를 완성한다.

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
- final review current head/digest에 결속
- unplanned product decisions > 0이면 successful terminal 불가
- ready/merge/auto-merge 수행 안 함
- report conclusion/evidence/verification/limitations/usage 순서 고정

### PR V3-8 — Adjustment and Ship

목적: PR 확인 후 전체 cycle을 재실행하지 않고 조정한다.

산출물:

- feedback impact analysis
- affected decision/unit invalidation
- selective planning + `CONFIRM PLAN`
- selective rebuild/reintegration
- `SHIP` final gate
- draft -> ready transition

Acceptance:

- unaffected accepted unit 재실행 0
- material feedback을 local coding change로 축소 불가
- ship 전 CI/head/final-review freshness 재검사
- merge/auto-merge 없음
- stale PR head에서 ship 거부

### PR V3-9 — Breaking cutover and v2 removal

목적: 검증된 V3를 `hwahap`의 유일한 구현으로 만들고 v2 runtime을 제거한다.

산출물:

- `skills/hwahap`을 V3 Skill/설치 문서/runtime 기준으로 전면 교체
- v2 `codex exec` templates와 orchestration hooks 제거
- v2 shell helpers/jq runtime 중 V3에서 사용하지 않는 구현 제거
- v2 schema/run/artifact compatibility code 0
- v2 전용 tests/workflow 제거 또는 V3 tests/workflow로 교체
- Hwahap-owned legacy config/hook entry cleanup
- Desktop install/update/uninstall flow
- Desktop compatibility matrix + release checklist

Acceptance:

- repository가 지원하는 Hwahap schema는 `hwahap/v3` 하나뿐
- 기존 v2 `.hwahap` state/artifact는 자동 import하지 않고 unsupported/restart message 반환
- `skills/hwahap` production path에서 nested `codex exec` reference 0
- v2 hook-based orchestration entrypoint 0
- v2/v3 selector와 compatibility adapter 0
- Hwahap-owned legacy Codex hook/MCP 설정은 제거/교체하되 unrelated user config 보존
- full Desktop E2E + manual release checklist 통과 후 cutover
- cutover rollback은 compatibility mode가 아니라 Git revert로만 수행

## 3. Test architecture

### 3.1 Deterministic unit tests

- contract/schema validation
- recommendation freshness/hash binding
- frontier/prerequisite graph
- traceability completeness
- state transition legality
- model routing/escalation
- DAG scheduling
- path/scope/secret policy
- report generation

### 3.2 Fake ACP harness

실제 모델 없이 다음을 결정적으로 생성한다.

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

pinned codex-acp로 최소 fixture repository를 실행한다.

- Luna one-file change
- read-only reviewer
- concurrent independent sessions
- dependent units
- PlanConflict
- network denial
- cancellation
- adapter restart/resume

Live tests는 nightly/manual lane에 둘 수 있지만 release checklist에서는 필수다.

### 3.4 Desktop E2E

| OS | Path | Required scenarios |
|---|---|---|
| macOS current-1/current | ChatGPT Desktop Codex | install, plan, cycle, resume, PR, adjust, ship |
| Windows current-1/current | ChatGPT Desktop Codex | install, quoting, process cleanup, resume |
| Linux | Codex CLI compatibility lane | core MCP/ACP/runtime regressions |

Desktop private endpoint는 테스트 대상이 아니다. 공개 Skill/MCP behavior만 검사한다.

### 3.5 Failure injection

- Hwahap process 종료
- codex-acp 종료
- Codex App Server 종료
- SQLite busy/corrupt copy
- disk full/permission denied
- worktree/patch conflict
- GitHub/gh failure
- CI pending/fail
- token/quota exhaustion
- user modifies PR head

각 case는 terminal state, resume action, retained evidence를 고정한다.

### 3.6 Coverage and mutation

- Rust line/branch coverage 수치 보고
- state transition/gate/permission/freshness mutation
- parser/schema fuzzing
- concurrency model testing 또는 loom 평가
- process/resource leak repeat test
- fmt/clippy/deny/audit

수치 목표는 implementation PR에서 toolchain probe 후 고정하되 gate 조건 mutation survival은 0을 목표로 한다.

## 4. Review gates

각 implementation PR은 다음 질문에 답해야 한다.

1. Parent LLM에게 orchestration 결정을 다시 넘기는가?
2. 제품 결정을 hidden default로 만드는가?
3. Luna로 충분한 작업에 상위 모델을 사용하는가?
4. stronger model이 필요한 작업을 비용 이유로 Luna-only로 끝내는가?
5. sandbox/permission만 믿고 postcondition 검사를 제거하는가?
6. resume 시 duplicate side effect가 가능한가?
7. current plan/current diff/current PR head에 evidence가 결속되는가?
8. Desktop 외 terminal 조작이 정상 UX에 필요한가?
9. 새 process/component 종류가 반드시 필요한가?
10. v2 호환성을 위해 dual-mode/adapter/legacy code path를 다시 추가하는가? (추가하면 안 됨)

한 항목이라도 설명되지 않으면 merge하지 않는다.

## 5. Release criteria

V3 breaking cutover 조건:

- P0 probe 완료와 문서화
- Plan completeness negative suite 통과
- recommendation freshness/property suite 통과
- Rust state/scheduler failure injection 통과
- nested `codex exec` 0 증명
- Luna-first routing receipts 확인
- macOS/Windows Desktop E2E 통과
- v2에서 계승하기로 한 invariant를 V3 native tests로 재검증
- 실제 repository canary run 5개 이상
- canary 모두 unplanned material decision 0
- orphan process 0
- draft PR -> adjustment -> ship E2E 통과
- v2 runtime/hook/schema compatibility path 제거를 static scan으로 확인
- cutover commit/PR의 Git revert 절차 확인

## 6. Current PR의 범위

이 문서와 상위 기획 PR은 설계 전용이다.

포함:

- V3 제품 계약
- lifecycle/architecture/model routing
- breaking replacement 전략
- implementation sequence
- acceptance/test/release gates

미포함:

- 현재 PR에서의 v2 code 변경(실제 제거는 V3-9 cutover에서 수행)
- Rust runtime scaffold
- Codex/MCP 설정 변경
- model call
- global Hwahap 설치 변경
- branch protection 변경
