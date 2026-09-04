# hwahap v3

구현 요청 하나를 `PLAN → PLAN FREEZE → AUTONOMOUS CODING → DRAFT PR → ADJUST | SHIP` 으로 끌고 가는
Codex 플러그인이다. Rust 바이너리 하나가 local STDIO MCP 서버이면서 동시에 `codex-acp` 어댑터를 모는
ACP 클라이언트다. 그 사이는 전부 `.hwahap/` 위의 결정적 상태 기계다.

v2와 호환되지 않는다. shell hook, `codex exec`, jq 런타임, `hwahap/v2` 스키마는 전부 제거되었고
지원하는 계약은 `hwahap/v3` 하나뿐이다. 기존 `.hwahap` 디렉터리를 만나면 변환하지 않고 명확한 오류를
낸다.

## 1. 한눈에 보기

| 단계 | 실행 주체 | 하는 일 | 사람이 하는 일 |
|---|---|---|---|
| PLAN | Economy(사실) + Deep(결정) | 저장소를 직접 조사하고, 결정마다 추천·근거·trade-off를 붙여 한 라운드에 전부 제시 | 답변만. 사실은 묻지 않는다 |
| PLAN FREEZE | Rust validator + Economy cold consumer + Critic | traceability·DAG·완결성 검사, 냉담한 재독, 적대적 검토 | `CONFIRM PLAN <challenge>` 정확히 입력 |
| CODING | Economy(구현) + Critic(리뷰) | unit을 위상 순서로 하나씩 구현→검증→리뷰→checkpoint commit | 없음. 목표는 질문 0회 |
| DRAFT PR | Deep(최종 리뷰) | full suite 1회, 브랜치 전체 최종 검토, draft PR 생성 | 결과 확인 |
| ADJUST / SHIP | — | 피드백을 결정으로 환원해 revision 증가, 또는 draft를 ready로 | `SHIP <challenge>` 정확히 입력 |

human gate는 `CONFIRM PLAN`과 `SHIP` 두 개뿐이다. 둘 다 내용에 결속된 digest challenge라서, 계획이
바뀌면 이전 challenge는 더 이상 맞지 않는다. 호스트 모델은 이 문장을 생성·보완·추론할 수 없다.

## 2. 설치

```sh
cargo build --release --manifest-path skills/hwahap/runtime/Cargo.toml
codex plugin marketplace add <이 저장소를 담은 marketplace 경로>
codex plugin add hwahap@<marketplace-name>
```

`bin/hwahap` 런처가 `HWAHAP_BIN` → `runtime/target/release/hwahap` →
`runtime/target/debug/hwahap` → `PATH` 순으로 바이너리를 찾고, 없으면 빌드 명령을 알려주고 실패한다.
진단은 전부 stderr로 나간다. stdout은 MCP 전송 채널이다.

필요한 것: Rust 1.90 이상, `git`, 인증된 `gh`, 그리고 PATH 위의 `codex-acp`. `.hwahap/`은 대상
저장소의 `.gitignore`에 있어야 한다.

## 3. 구조

```
skills/hwahap/                     플러그인 루트 (= 설치 단위)
├── .codex-plugin/plugin.json      Codex 매니페스트. 공식 validate_plugin.py 통과
├── .mcp.json                      local STDIO MCP 서버 하나
├── bin/hwahap                     바이너리를 찾아 exec 하는 POSIX sh 런처
├── skills/hwahap/SKILL.md         thin dispatcher. 25줄 (게이트는 40줄)
├── tests/gates.sh                 정적 단순성 게이트
├── PLATFORM.md                    실측으로 확인한 플랫폼 사실 (V3-0 증거)
└── runtime/                       Rust 크레이트
    ├── src/                       모듈당 책임 하나
    └── tests/
        ├── common/mod.rs          실제 저장소 + gh stub + 스크립트 에이전트
        ├── cycle.rs               스크립트로 도는 전체 사이클
        └── surface.rs             크레이트 밖에서 본 MCP 표면
```

`SKILL.md`가 `skills/hwahap/skills/hwahap/`에 중첩된 것은 Codex 플러그인 규약이 스킬을
`<plugin>/skills/<name>/SKILL.md`에서 찾기 때문이다. 근거는 [PLATFORM.md](PLATFORM.md) §3에 있다.

런타임 모듈은 각각 한 가지만 안다.

| 모듈 | 책임 |
|---|---|
| `canonical` | canonical JSON과 digest. challenge가 나오는 유일한 곳 |
| `plan` | `hwahap/v3` 계약 타입. 답변 신선도 규칙 |
| `answer` | 사용자 답변 문법. 확인 문장을 만들어낼 수 없는 유일한 관문 |
| `frontier` | 지금 물을 수 있는 질문 |
| `validate` | freeze 게이트와 unit 위상 정렬 |
| `render` | 결정적 `plan.md` |
| `state` | `run.json` 원자적 스냅샷 + `events.jsonl` hash chain |
| `profile` | 고정 profile 3개. `none`/`low`/`max`는 타입상 존재하지 않는다 |
| `acp` | 어댑터 1개, 동시 세션 1개, profile fail-closed 적용 |
| `agentresult`·`proposal` | agent가 낼 수 있는 strict JSON 계약 |
| `prompts` | 역할별 프롬프트. 같은 입력이면 같은 바이트 |
| `git`·`forge` | 실제 관찰면. 성공은 여기서만 판정된다 |
| `engine` | 상태 기계 |
| `mcp` | tool 3개와 `instructions` |

## 4. 설계 결정

**MCP tool은 3개뿐이다.** `plan`, `cycle`, `retry`, `spawn_worker` 같은 tool은 전부 스케줄링·승인
판단을 호출한 모델에게 되돌려준다. 그 판단은 Rust 상태 기계가 한다.

**cross-tool protocol의 단일 출처는 MCP `instructions`다.** `SKILL.md`도, 어떤 참조 문서도 같은
규칙을 반복하지 않는다.

**추천은 기본값이 아니다.** 추천은 표시되고, `C<n>=REC`가 있어야 확정된다. 추천 내용이 바뀌면 기존
`REC` 답변은 stale이 되지만, 명시적 `ALT<m>` 답변은 그대로다. 두 개의 digest가 이 차이를 만든다.

**LLM의 주장은 증거가 아니다.** worker의 JSON은 control metadata일 뿐이고, 테스트 통과는 호스트가
명령을 실행해 exit status로, 변경 범위는 git diff로 판정한다. 리뷰 세션이 working tree를 건드렸으면
그 verdict는 폐기된다.

**profile은 적용되거나 run이 멈춘다.** ACP v1에는 model/effort 필드가 없다. 둘 다 session config
option이라, model을 먼저 설정하고(효어트 목록이 모델에 따라 달라진다) 그다음 effort를 설정한 뒤
echo된 상태를 다시 읽어 확인한다. `xhigh`가 없으면 `blocked: unsupported_profile`이지 `high`로
내려가지 않는다.

**SQLite도 daemon도 없다.** 저장소당 active run 하나뿐이므로 `run.json`(원자적 교체)과
`events.jsonl`(hash chain)이면 충분하다. 스냅샷이 journal보다 앞서 있으면 fail-closed다.

**crash 후에는 resume하지 않는다.** in-flight ACP session ID는 durable state가 아니다. 마지막
accepted checkpoint로 reset하고 현재 unit을 새 세션으로 다시 실행한다.

## 5. 모델·effort 정책

| Profile | 모델 | Effort | 담당 |
|---|---|---|---|
| Economy | `gpt-5.6-luna` | `medium` | 사실 조사, cold consumer, 구현, 테스트, 첫 rework |
| Critic | `gpt-5.6-terra` | `high` | plan 적대적 검토, unit 리뷰, 반복 실패 진단 |
| Deep | `gpt-5.6-sol` | `xhigh` | 추천·plan 합성, PlanConflict replan, 최종 리뷰 |

retry는 effort escalation이 아니다. 같은 profile을 유지한다. `.hwahap/config.toml`의
`[profiles.*]`로 model과 effort를 한 단위로만 바꿀 수 있다. model만 바꾸고 effort를 이전 모델 기준으로
남기는 configuration skew는 파싱 단계에서 거부된다.

## 6. 테스트 규칙

구현은 단순하게, 테스트는 엄격하게.

- 모든 분기와 모든 오류 경로에 그것을 유발하는 테스트가 있다.
- 단언은 `is_ok()`가 아니라 정확한 값과 오류 variant에 한다.
- 결정적이어야 하는 출력은 입력 순서를 섞어도 같은 바이트임을 테스트한다.
- 파일시스템은 `tempfile::TempDir`, 시계는 `FixedClock`을 쓴다.
- 프로덕션 코드 한 줄을 지웠을 때 실패하는 테스트가 없으면 그 테스트는 장식이다.

사이클 전체는 모델 없이 검증한다. `runtime/tests/common/mod.rs`의 `Script`가 `Sessions` seam에서
ACP 클라이언트를 대신하므로, rework·범위 이탈 reset·plan conflict·crash 복구·ship 게이트가 전부
결정적으로 몇 밀리초 만에 돈다. 임시 저장소는 진짜 git 저장소이고 `gh`는 저장소 상태를 그대로 되읽는
stub이라, "에이전트의 주장이 아니라 저장소 상태로 판정한다"는 주장 자체가 시험 대상이 된다.

```sh
cargo test --manifest-path skills/hwahap/runtime/Cargo.toml --all-targets
cargo clippy --manifest-path skills/hwahap/runtime/Cargo.toml --all-targets -- -D warnings
skills/hwahap/tests/gates.sh
```

`gates.sh`는 설계를 숫자로 고정한다. tool 3개, `SKILL.md` 40줄 이하, profile 3개와 그 정확한
model/effort, `codex exec` 참조 0, lifecycle hook 0, SQLite/HTTP server 의존성 0, ACP unstable
feature 0, daemon 정의 0.

## 7. 하지 않는 것

merge와 auto-merge, force-push, history rewrite, 상시 daemon, HTTP MCP transport, 병렬 worker pool,
worker용 내부 MCP server, ACP proxy/conductor/protocol v2, cross-project memory, v2 아티팩트 변환.
