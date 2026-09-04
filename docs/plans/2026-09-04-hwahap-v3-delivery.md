# Hwahap V3 구현·검증 계획

- 상위 기획: [2026-09-04-hwahap-v3.md](2026-09-04-hwahap-v3.md)
- 상태: 제안
- 전달 방식: 작은 구현 단계로 검증하되 마지막 cutover에서 v2를 전면 제거한다.

## 1. 구현 전략

기존 계획의 10개 구현 PR과 다수 subsystem을 6개 단계로 줄인다.

```text
V3-0 official-surface probes
  -> V3-1 plan contract
  -> V3-2 thin plugin + file state
  -> V3-3 sequential ACP coding loop
  -> V3-4 review, PR, adjust, ship
  -> V3-5 breaking cutover
```

`main`에는 V3-5 전까지 v2가 남는다. V3 작업은 전용 integration branch에서 검증한다. 사용자에게 v2/v3 selector나 dual-mode를 제공하지 않는다.

각 단계는 green 상태로 끝나야 한다. 이후 단계가 이전 단계의 red CI를 고치는 전달 방식은 허용하지 않는다.

## 2. V3-0 — 공식 surface probe

목적: Desktop와 ACP의 실제 behavior를 확인하고 불필요한 fallback을 설계하지 않는다.

### 확인할 것

1. ChatGPT Desktop가 local STDIO MCP process를 언제 시작·종료하는가.
2. 하나의 MCP tool call이 coding cycle 동안 유지되는가.
3. Host deadline/interruption 뒤 새 call이 같은 local files에서 복구 가능한가.
4. MCP initialize `instructions`가 Codex의 tool 사용에 반영되는가.
5. official Rust ACP SDK stable v1 client가 pinned `codex-acp`와 handshake하는가.
6. 하나의 adapter process에서 session을 순차 생성·종료할 수 있는가.
7. Model, reasoning effort, cwd, sandbox mode가 session별로 적용되는가.
8. Existing ChatGPT login을 사용하면서 Hwahap이 credential bytes를 읽지 않는가.
9. Cancellation/drop이 adapter와 Codex child process tree를 종료하는가.
10. macOS와 Windows에서 path quoting과 process cleanup이 일치하는가.

### 의도적으로 확인하지 않을 것

- Concurrent multi-session
- ACP protocol v2
- MCP-over-ACP
- HTTP transport
- MCP Tasks
- Desktop private App Server endpoint

위 기능은 초기 architecture에 사용하지 않기 때문에 probe 범위에서도 제외한다.

### 산출물

- `docs/evidence/hwahap-v3/platform.md`
- version/date/OS/command/expected/observed를 가진 probe records
- 최종 dependency/version pin

### Acceptance

- 모든 required probe가 반복 가능한 command 또는 test로 남음
- credential contents가 log/artifact에 없음
- cancellation 반복 실행 후 orphan process 0
- 실패한 probe는 fallback을 즉시 추가하지 않고 architecture assumption을 수정함

## 3. V3-1 — Plan contract

목적: Blackbox-Zero와 recommendation-first planning을 runtime과 독립적으로 고정한다.

### 구현

- `hwahap/v3` `plan.json` schema
- Fact, Decision, Recommendation, Scenario, Acceptance, Unit, Test records
- 12-surface applicability checklist
- frontier derivation
- `C<n>=REC`, `ALT`, `OTHER`, `UNKNOWN`, `NA`
- `recommended`, `no_recommendation`, `probe_required`
- challenge-bound `CONFIRM PLAN <digest>`
- deterministic `plan.md` renderer
- traceability/DAG/completeness validator
- Luna cold-consumer prompt contract
- Terra plan-review prompt contract

### 단순화 규칙

- 12개 surface는 stage object가 아니다.
- Plan lifecycle은 Inspect, Decide, Prove, Freeze 네 상태뿐이다.
- 여러 critic agent 대신 Terra review 하나와 deterministic validator 하나를 사용한다.
- 별도 answers database를 만들지 않는다. User answers는 hash-chained event로 기록하고 `plan.json`에 materialize한다.

### Acceptance

- Recommendation만 있고 user answer가 없으면 unresolved
- Recommendation content 변경 시 기존 `REC` answer stale
- Open fact/probe/assumption이 있으면 freeze 불가
- Requirement, acceptance, unit, test 중 orphan node가 있으면 freeze 불가
- Cold consumer가 새 product decision을 요구하면 freeze 불가
- Plan output이 같은 입력에서 byte-stable
- Negative/property/mutation tests가 모든 gate를 뒤집어 검증

## 4. V3-2 — Thin Desktop plugin과 file state

목적: ChatGPT Desktop에서 Hwahap을 하나의 capability로 설치하고 호출한다.

### Plugin shape

```text
Hwahap plugin
├── .codex-plugin/plugin.json
├── skills/hwahap/SKILL.md
├── .mcp.json
└── hwahap binary distribution metadata
```

### Skill

- `SKILL.md` 40줄 이하
- trigger, exact user-input forwarding, tool-loop behavior만 포함
- Architecture, model routing, Git algorithm은 포함하지 않음
- Cross-tool protocol은 MCP `instructions`가 소유

### MCP tools

정확히 세 개만 제공한다.

1. `hwahap_step`: start, answer, plan advance, build advance, adjust
2. `hwahap_status`: read-only projection
3. `hwahap_ship`: explicit consequential PR-ready action

### File state

```text
.hwahap/
├── plan.json
├── plan.md
├── run.json
├── events.jsonl
├── artifacts/
├── worktree/
└── report.md
```

- 한 repository에서 active run 하나
- `run.json`: fsync + atomic rename
- `events.jsonl`: sequence + previous hash
- SQLite 없음
- daemon 없음
- lifecycle hooks 없음

### Acceptance

- ChatGPT Desktop에서 terminal 없이 skill 선택과 PLAN 시작 가능
- Tool descriptions가 서로 overlap하지 않음
- `status`만 `readOnlyHint=true`
- `ship`은 별도 confirmation challenge 없이는 실행 불가
- Skill이 `CONFIRM PLAN` 또는 `SHIP`을 생성하지 않는 behavioral test
- Process 재시작 후 `run.json`/journal에서 같은 phase 복구
- Same-repo second run은 명확히 거부

## 5. V3-3 — 순차 ACP coding loop

목적: nested `codex exec`와 per-unit worktree 없이 frozen plan을 구현한다.

### Runtime

- 하나의 Rust package
- Tokio
- official ACP Rust SDK stable v1
- pinned `codex-acp`
- active run 동안 adapter process 하나
- 동시에 active한 ACP session 하나
- unit attempt/review마다 fresh session
- session resume/load 사용 안 함

### Git model

```text
one run
  = one hwahap/<goal-id> branch
  = one .hwahap/worktree
  = accepted unit checkpoint commits
```

Unit loop:

1. DAG의 다음 ready unit 선택
2. Last checkpoint에서 Luna worker session 시작
3. Strict JSON final result 수집
4. Changed path와 실제 unit test 검증
5. Terra read-only review
6. Pass면 checkpoint commit
7. Fail이면 reset 후 Luna rework 한 번
8. Persistent failure면 Terra diagnosis 후 blocked 또는 한 번의 수정 attempt

### Fixed model roles

- Luna: facts, cold consumer, implementation, tests, first rework
- Terra: plan critic, unit reviewer, persistent-failure diagnosis
- Sol: plan/recommendation synthesis, PlanConflict replan, final review

Numeric risk score와 범용 router는 만들지 않는다.

### Result contracts

Worker:

```json
{"status":"completed|plan_conflict|failed","summary":"...","conflict":null}
```

Reviewer:

```json
{"verdict":"pass|fail","findings":[]}
```

Worker-facing MCP server는 없다. JSON이 malformed하면 fail-closed한다. Test/patch 성공은 agent result가 아니라 host observation으로 판정한다.

### Crash recovery

- In-flight ACP session ID를 저장하지 않음
- Process crash 시 working tree를 last accepted checkpoint로 reset
- Current unit을 fresh session으로 재실행
- Accepted commits는 재실행하지 않음

### Acceptance

- production path의 `codex exec` 호출 0
- unit별 worktree 생성 0
- simultaneous worker session 최대 1
- out-of-scope diff는 commit 전 reset
- failed/rejected unit commit 0
- accepted checkpoint commit에 unit ID와 plan digest 포함
- crash point별 accepted commit 손실 0
- cancellation 뒤 adapter/Codex process leak 0

## 6. V3-4 — Final review, PR, adjustment, ship

목적: 같은 branch/worktree에서 cycle을 완료하고 사용자가 PR에서 조정한다.

### Completion

- 모든 unit accepted 후 full suite 한 번
- Sol final review 한 번
- Scope/secret/plan-digest/freshness gate
- Branch push
- Draft PR 생성
- `report.md`와 structured summary

별도 integration worktree, patch merge engine, integration lock은 만들지 않는다.

### PlanConflict

- Worker result가 `plan_conflict`이면 diff가 비어 있어야 함
- Affected unit과 dependent를 park
- Independent ready unit은 계속 실행
- 실행 가능한 unit이 끝난 뒤 conflict를 한 번에 반환
- Resolution은 PLAN revision과 새 `CONFIRM PLAN`을 요구

### Adjustment

- Feedback을 decision/acceptance/unit에 매핑
- Material change만 selective PLAN round
- Existing branch 위에 correction commits 추가
- Unaffected accepted unit 재실행 없음
- Affected unit/dependent 검증과 full suite/final review 재실행
- Force-push/history rewrite 없음

### Ship

`hwahap_ship`은 다음을 확인한다.

- exact `SHIP <digest>` challenge
- current PR head
- required CI success
- current plan digest
- open conflict/finding 0
- final review freshness
- scope/secret gate

통과하면 draft PR을 ready로 전환한다. Merge와 auto-merge는 범위 밖이다.

### Acceptance

- Successful cycle의 unplanned material decision 0
- Final review가 current head에 결속
- Draft PR 이전에 full suite와 final review 필수
- Adjustment가 unrelated unit을 다시 실행하지 않음
- Stale head 또는 stale review에서 ship 거부
- PR ready 외 external mutation 없음

## 7. V3-5 — Breaking cutover

목적: V3를 유일한 Hwahap 구현으로 만들고 v2를 제거한다.

### 제거

- v2 `codex exec` templates
- v2 UserPromptSubmit/PreToolUse/PostToolUse/Stop orchestration
- v2 shell helper
- V3에서 사용하지 않는 jq runtime
- v2 schema/artifact reader
- v2 run resume
- v2 tests/workflow
- v2/v3 selector와 compatibility adapter

### 교체

- `skills/hwahap/SKILL.md` -> thin dispatcher
- 설치 문서 -> plugin + local STDIO MCP
- CI -> Rust, contract, fake ACP, live smoke, Desktop checklist
- README -> PLAN/FREEZE/CODING/ADJUST/SHIP

### Acceptance

- Supported schema는 `hwahap/v3` 하나
- Production Hwahap path의 `codex exec` reference 0
- Hwahap-owned lifecycle hook 0
- SQLite/HTTP/daemon/internal worker MCP dependency 0
- ACP proxy/conductor/unstable feature 0
- MCP tools 정확히 3개
- `SKILL.md` 40줄 이하
- Existing v2 `.hwahap`은 자동 import하지 않고 clear error 반환
- Unrelated Codex/MCP/user config 보존
- Rollback은 cutover PR Git revert로 검증

## 8. Test architecture

### 8.1 Contract tests

- recommendation freshness/hash binding
- frontier prerequisite graph
- surface coverage
- traceability completeness
- challenge validation
- state transition legality
- deterministic rendering

### 8.2 Fake ACP agent

실제 모델 없이 다음을 생성한다.

- text/reasoning/tool events
- valid/invalid JSON final response
- permission request
- file change
- disconnect
- timeout
- cancellation race
- process crash

### 8.3 Live smoke

Pinned adapter로 작은 fixture repository를 실행한다.

- Luna one-file implementation
- Terra read-only review
- dependent sequential units
- PlanConflict
- network denial
- adapter crash/current-unit restart
- draft PR flow

Live model test는 일반 PR CI에 항상 넣지 않아도 되지만 cutover release checklist에는 필수다.

### 8.4 Desktop E2E

| OS | Required |
|---|---|
| macOS current/current-1 | plugin install, PLAN, resume, PR, adjust, ship |
| Windows current/current-1 | install, path quoting, restart, process cleanup |
| Linux CLI lane | MCP/ACP/runtime regression |

### 8.5 Failure injection

- MCP process 종료
- adapter/Codex child 종료
- atomic-write 직전/직후 종료
- malformed/truncated journal tail
- disk full/permission denied
- worktree dirty/reset failure
- test timeout
- GitHub/CI failure
- user-modified PR head

### 8.6 Static simplicity gates

다음을 CI에서 숫자로 고정한다.

- MCP tool count = 3
- Skill physical lines <= 40
- active worker sessions <= 1 in tests
- `codex exec` production references = 0
- lifecycle hook definitions = 0
- SQLite dependencies = 0
- HTTP server dependencies = 0
- ACP unstable features = 0
- Hwahap-owned daemon/service definitions = 0

## 9. Release gate

Breaking cutover 전 다음이 모두 필요하다.

- V3-0 probe 완료
- Contract negative/property/mutation suite 통과
- Atomic state/journal recovery tests 통과
- ACP process/cancellation leak tests 통과
- Luna-first fixed-role receipts 확인
- macOS/Windows Desktop E2E 통과
- 실제 repository canary run 5개 이상
- Canary의 unplanned material decision 0
- Draft PR -> adjustment -> ship E2E 통과
- Static simplicity gates 통과
- Cutover Git revert rehearsal 통과

## 10. Review 질문

각 PR은 다음에 답한다.

1. 이 기능이 PLAN/FREEZE/CODING/ADJUST/SHIP에 필수인가?
2. 새로운 process, storage, protocol, tool을 추가하지 않고 구현할 수 없는가?
3. Parent LLM에게 scheduling이나 approval 결정을 다시 넘기는가?
4. Hidden default 또는 unplanned material decision 경로가 생기는가?
5. Luna로 충분한 routine work에 상위 모델을 사용하는가?
6. LLM claim을 deterministic evidence 대신 신뢰하는가?
7. Crash 뒤 current unit 재실행보다 session resume가 정말 필요한가?
8. One worktree/sequential loop보다 복잡한 Git/concurrency 구조가 정말 필요한가?
9. Skill, MCP instructions, runtime에 같은 규칙을 중복하는가?
10. V2 compatibility code를 다시 추가하는가?

필수성을 입증하지 못한 추가 subsystem은 merge하지 않는다.
