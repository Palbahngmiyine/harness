# Hwahap 조율 설계: 채택할 규칙과 검증 계획

2026-09-05 조사. 판단 순서는 **명료함 → 엄격한 테스트 → 쉬운 재현·반복 수정 → 총비용 효율**이다.
현재 native Codex 실행과 작은 Rust 상태 기계를 유지하고, 실패 경계의 검증부터 강화한다.
에이전트 실행 수명은 Codex가 소유하고, Hwahap은 승인·검증·복구에 집중한다.

## 근거와 확인 범위

- KiroCrew는 커밋 [`5f5e3dec480571f35dc72da06213ac8983ffc0af`][kc]의 문서·소스·테스트를 읽었다. 해당 코드를 설치하거나 실행하지 않았다.
- Hwahap 비교 기준은 `662c97e3e99c6cd12ef62facd52e5d962c7e03a7`의 [README](../skills/hwahap/README.md), [native broker](../skills/hwahap/runtime/src/native/broker.rs), [host](../skills/hwahap/runtime/src/native/host.rs), [결과 계약](../skills/hwahap/runtime/src/agentresult.rs), [비용 집계](../skills/hwahap/runtime/src/cost.rs)다.
- 아래에서 외부 구현은 **소스 확인**, 회귀 검증한 변경은 **이번 구현**, 추가 실험은 **후속 제안**으로 구분한다. 소스 존재나 테스트 코드 열람을 실행 성공으로 계산하지 않는다.
- 실제 Codex canary 및 전체 실행의 한계는 [PLATFORM.md](../skills/hwahap/PLATFORM.md)에 따로 기록되어 있다. 이 문서는 그 실행을 다시 검증하지 않았다.

## 네 원칙을 실행 규칙으로 바꾸기

| 우선순위 | 공식 자료에서 확인한 내용 | Hwahap에 적용할 판단 |
|---|---|---|
| 1. 명료성 | [Rob Pike의 규칙][rob]은 측정 전 최적화를 피하고 단순한 자료구조·알고리즘을 택하도록 권한다. | 실행 상태·승인·결과의 소유자를 하나씩 정한다. 이미 있는 Codex 기능을 다시 구현하기 전에 실제 빈틈을 증명한다. |
| 2. 엄밀한 테스트 | [SQLite §3·§5][sqlite]는 실패 주입과 버그를 드러내는 회귀 테스트를 설명한다. | 정상 경로뿐 아니라 잘못된 입력·중단·재전송에서 상태와 외부 부작용을 검사한다. |
| 3. 쉬운 재현·반복 수정 | [KiroCrew의 취소 테스트][kc-race]는 이벤트로 중단 시점을 고정하고 실제 전달 완료를 확인한다. | 재현 입력, 시작 Git 상태, 실패 단계, 기대 상태, 실제 결과를 작은 fixture로 남긴다. 실패 테스트→최소 수정→관련 재검증 순서로 진행한다. |
| 4. 총비용 효율 | [Uber의 측정·모델 선택][uber]은 완료 결과당 비용과 품질·지연을 함께 본다. 초기 지시와 도구 정의·불필요한 반복도 비용 요인이다. | 같은 성공 조건에서 실패·취소·재작업·부모 전달 비용까지 포함한다. 저렴한 모델이나 호출 감소만으로 절감을 선언하지 않는다. |

[SQLite §7.7][sqlite-coverage]는 100% MC/DC 유지가 일반 애플리케이션에는 비용에 맞지 않을 수 있다고 명시한다.
MC/DC는 각 조건이 판단 결과에 독립적으로 영향을 주는지 확인하는 커버리지 방식이다.
따라서 SQLite의 전체 테스트 인프라나 커버리지 수치를 Hwahap의 목표로 복사하지 않는다.
핵심 상태 전이의 실패 주입과 이미 발견한 버그의 회귀 방지를 먼저 채택한다.
Uber의 자동 스킬 개선은 글의 “What’s Next?”에 진행 중 과제로 적혀 있다. 완성된 자율 학습 효과의 증거로 사용하지 않는다.

## KiroCrew에서 채택할 다섯 가지

| 소스에서 확인한 장치 | Hwahap 적용 | 이득과 제한 |
|---|---|---|
| `TerminalCoordinator`는 완료 기록, 부모 보고, 슬롯 반환에 별도 일회성 표식을 둔다. [소스][kc-terminal] | `dispatch_id`에 묶인 완료 기록·continuation 전달·잠금 해제를 별개 불변식으로 검사한다. | 취소와 정상 종료가 겹쳐도 이중 처리나 누락을 구별한다. KiroCrew의 전체 reaper는 필요 없다. |
| 보고 중 취소 테스트가 `Event`로 정확한 지점을 제어하고 전달 완료 1회를 검증한다. [테스트][kc-race] | 완료 저장 실패와 취소 중 잠금 유지 테스트를 추가했다. 수동 poll로 정확한 시점을 고정하고 저장·소비·종료 상태를 확인한다. | 재현이 쉽고 수정 전후 비교가 가능하다. 실제 모델·프로세스 종료 검증은 별도로 남는다. |
| `continue_conversation_impl`은 새 실행 ID와 기존 대화 key를 분리하고 busy/gone을 구별한다. [소스][kc-continue] | 후속 실험에서 같은 구현자의 수정에 native follow-up을 사용하되 새 attempt를 기록한다. | 유효한 문맥을 재사용할 수 있다. 독립 리뷰에는 새 에이전트를 쓰고, 계획·모델·경로가 달라지면 재사용하지 않는다. |
| 완료 metadata에 outcome과 requested/resolved model이 있다. [소스][kc-meta] | strict 결과 JSON을 유지하고 요청·실제 적용·미확인을 구분한다. | 설명 문구와 상태 해석이 분리된다. 호스트가 제공하지 않는 실제 모델·사용량을 자기보고로 확정하지 않는다. |
| 작업 snapshot에 repo/worktree/branch/commit 정체성을 넣고, 오래된 저장 순서를 거부한다. [소스][kc-snapshot] | 기존 run·plan digest·Git 기준점·dispatch를 복구 입력으로 유지한다. | 다른 작업의 상태를 재사용할 위험을 줄인다. 단일 active run 구조에 새 DB나 비동기 저장 계층을 추가하지 않는다. |

KiroCrew의 `build_task_prompt`는 Git 요약과 직전 오류를 넣어 처음부터 다시 시작하지 않도록 한다. [소스][kc-prompt]
현재 Hwahap은 해당 unit의 승인된 결정·완료 조건·경로·검증 명령과 직전 거부 사유를 전달한다. 실패 diff 전체를 재시도에 자동 전달하는 기능은 없다.
전체 대화를 무조건 복사하거나 길이를 임의로 잘라 중요한 계획을 없애는 방식은 채택하지 않는다.

## 그대로 복제하지 않을 다섯 가지

| 소스에서 확인한 장치·행동 | 채택하지 않는 이유 | 대신 유지할 것 |
|---|---|---|
| 공유 ACP runtime·세션 pool·전용 provider 우회. [소스][kc-session] | KiroCrew가 호스트를 소유해서 필요한 계층이며 native Codex와 중복된다. | 생성·대기·중단은 Codex, 계획·증거·승인은 Rust가 소유한다. |
| Markdown 체크된 작업 제목으로 checkpoint 완료를 찾는다. [소스][kc-checkpoint] | 이 경로는 제목이 같아도 계획·Git 내용이 바뀐 경우를 결속하지 않는다. | 승인된 plan digest와 정확한 실행 정체성을 검사한다. 보고용 Markdown은 상태 원본으로 읽지 않는다. |
| `self_review`가 diff를 8,000자로 제한하고 빈/불완전 응답 또는 예외에서 통과할 수 있다. [소스][kc-review] | 검토 실패를 통과로 바꾸면 검증 강도가 떨어진다. | malformed·누락·오류 결과를 명시적으로 거부하고 실제 diff·명령 종료 상태를 확인한다. |
| `git add -A`, `reset --hard HEAD~1`, worktree 강제 제거. [소스][kc-git] | KiroCrew의 독립 workspace 가정을 함께 요구한다. 사용자 변경 보존 계약에 일반화할 수 없다. | 격리 worktree에서 변경 경로를 먼저 검증한 뒤 host가 commit한다. 저장소 작업에서는 작업 소유 파일만 stage한다. 복구가 사용자 변경을 폐기하지 않게 한다. |
| 짧은 실패 설명에서 모델이 장기 lesson을 생성·저장한다. [소스][kc-lessons] | 해당 경로에는 규칙의 독립 재현·검증이 필수 조건으로 없다. | run 내부의 실패→수정→회귀 테스트 기록을 남긴다. 자동 memory·skill 학습과 규칙 승격은 도입하지 않는다. |

## native Codex를 사용하는 권장 소유권 흐름

[OpenAI 공식 문서][codex]는 native 하위 에이전트 생성·후속 지시·대기·종료를 설명한다.
아래는 그 기능 위에서 Hwahap이 맡을 범위이며, 현재 호스트의 실제 도구 계약이 우선한다.

1. **Rust:** 승인된 plan·unit·역할·profile·절대 경로를 실행 요청으로 저장하고 `dispatch_id`를 발급한다.
2. **Codex 호스트:** 요청대로 native 에이전트를 만들고 즉시 ID를 등록한다. 등록 전 단절 시 같은 요청을 바로 재생성하지 않는다.
3. **하위 에이전트:** 제한된 작업을 수행하고 strict JSON 결과를 반환한다. 통과의 최종 판정권은 없다.
4. **Codex 호스트:** 에이전트와 남은 명령의 종료를 확인하고 정확한 ID의 완료와 제공 가능한 usage를 전달한다.
5. **Rust:** 완료를 저장한 뒤 상태 전이에 소비한다. 테스트 exit status·Git diff·독립 리뷰로 unit 통과를 판단한다.
6. **단절·timeout:** 상태 확인→해당 작업 종료 확인→정확한 dispatch의 stop acknowledgment→복구 순서다. timeout 자체는 종료 증거가 아니다.

현재 spawn 도구에는 별도 `cwd`·`sandbox` 인수가 없으므로 경로·read-only는 지시에 포함하고 Git 상태를 검사한다.
이는 OS 수준 격리나 모든 외부 부작용의 방지를 입증하지 않는다. 단일 저장소의 active run은 하나로 유지한다.

## 현재 구현과 수정·제안의 경계

| 분류 | 내용 | 현재 증거의 한계 |
|---|---|---|
| 기준 소스에 구현됨 | native 요청 선저장, agent 등록, 일치하는 완료, 동일 완료 재전송, stop acknowledgment, 실행 잠금, strict JSON, 요청·사용량 집계 | [native 테스트](../skills/hwahap/runtime/tests/native_surface.rs)는 통제한 결과를 사용한다. 실제 모델 전체 사이클 성공과 다르다. |
| 이번 구현 | 임시 probe 산출물이 Git history에 남는 문제 | probe 종료 뒤 파일·HEAD뿐 아니라 전체 history에 산출물이 없는지 회귀 테스트로 확인한다. |
| 이번 구현 | 충돌·malformed 답변이 섞인 confirmation의 처리 | 잘못된 승인 문장은 승인되지 않고 상태·외부 부작용을 바꾸지 않아야 한다. |
| 이번 구현 | stale confirmation을 재사용하는 문제 | 승인 직전에는 재검토·새 challenge를 요구한다. 승인 이후에도 구현·최종 검증·SHIP에서 실제 내용 digest와 승인 기록을 비교한다. |
| 이번 구현 | 같은 요청·시각의 run ID와 archive 충돌 | 성공 후 재실행과 브랜치 생성 전 실패 후 재실행을 각각 3회 검증했다. 이전 run ID·journal·artifacts를 보존한다. |
| 이번 구현 | adjustment 이후 구조 재생성과 기존 draft PR 재사용 | requirements/acceptance/units/tests를 재생성한다. 변경 없는 독립 작업은 유지하고 변경 작업의 의존 작업은 재검증한다. 같은 draft를 갱신하며 ready PR이면 push 전에 거부한다. |
| 이번 검증 | 완료·pending 저장 실패 후 재시도, 취소 완료 전 lock·pending 유지 | native 통합 테스트 10개 통과. 실제 외부 프로세스 종료·전원 장애를 검증한 결과는 아니다. |
| 후속 제안 | 동일 구현자 follow-up 재사용, 나머지 프로세스 중단 경계 | 현재 기능이나 완료된 검증으로 계산하지 않는다. 아래 통과 조건으로 작은 변경부터 검증한다. |

최초 다섯 결함에 더해 적대적 재검토에서 브랜치 생성 전 run ID 재사용과 의존 작업의 오래된 통과 기록을 재현·수정했다. draft 갱신의 ready 상태도 push 전에 검사한다. GitHub 조회와 push 사이 외부 상태 변경까지 원자적으로 막는 것은 아니다.

## 채택 순서와 재현 테스트 표

이번 결함은 고정 입력으로 실패를 재현한 뒤 같은 테스트를 통과시켰다. native 저장 실패·취소 처리 경계도 직접 검사했다.
그 뒤에도 중복 생성·문맥 재구성이 실제 비용의 주요 원인일 때만 follow-up 재사용을 실험한다.
재현 기록에는 base commit, 입력, test 이름, 실패 단계, expected/actual, 산출물 위치를 포함한다.

| 순서·상태 | 재현 입력·중단 지점 | 반드시 관찰할 결과 |
|---|---|---|
| 1·검증 완료 | 임시 파일을 만드는 probe unit을 실행 | 파일·HEAD tree·전체 Git history에 임시 산출물이 남지 않고 이후 unit은 정상 진행한다. |
| 1·검증 완료 | 충돌·malformed 답변과 승인 혼합; 승인 전·후 계획 내용 변조 | 잘못된 입력은 저장 상태를 유지한다. 승인 전 내용 변경은 재검토·새 challenge를 요구한다. 승인 후 변경은 에이전트·명령·발행 전에 거부한다. |
| 1·검증 완료 | 고정 clock에서 연속 run 생성 | 서로 다른 run ID·브랜치, 보관된 plan·journal·report·artifacts 유지. |
| 1·검증 완료 | 기존 draft가 있는 상태에서 unit 구조를 바꾸는 adjustment | 새 구조 검증·재승인, 무관한 작업 재사용, 변경 작업과 의존 작업 재검증, create 1회·edit 1회. |
| 2·후속 테스트 | 요청 저장 후 생성/등록 중단; 완료 저장 후 소비 전 중단 | 중복 spawn 없음, 미확인 작업은 종료 확인 전 재시작 안 함, 같은 완료는 한 번만 소비. |
| 2·검증 완료 | completion/pending 저장 경로를 막음; task 취소 전후를 수동 poll | 저장 실패 시 미전달, 복구 후 동일 결과 전달·동일 재전송 수용. 취소 완료 전 lock·pending 유지. 새 테스트에 sleep 없음. |
| 3·후속 실험 | 동일 unit 수정에서 fresh spawn과 follow-up 비교; busy/gone 각각 주입 | 새 attempt 기록, busy에서 중복 실행 없음, gone에서 명시적 새 실행, 독립 리뷰 유지. |

검증 명령은 `cargo test --manifest-path skills/hwahap/runtime/Cargo.toml --all-targets`, 같은 manifest의 `cargo clippy --all-targets -- -D warnings`, `skills/hwahap/tests/gates.sh`다. 수정한 경계를 먼저 확인한 뒤 전체 검사를 수행했다.
실제 Codex 전체 실행은 별도 acceptance run으로 기록한다. stub 통과를 실제 모델 성공이나 비용 절감으로 대체하지 않는다.

## 총비용의 성공 분모와 관측 항목

성공 분모는 **같은 승인 범위와 필수 검증을 만족해 review 가능한 draft PR까지 전달한 요청 수**로 제안한다.
모델 응답 1개, 테스트 호출 1개, 열린 PR 수만으로 성공을 세지 않는다. 요구가 다른 작업은 같은 집계에 섞지 않는다.

| 지표 | 기록 방법·해석 |
|---|---|
| 품질 | 성공/전체 시작 요청, 잘못된 통과, 계획 이탈, 회귀, 사용자 수정·개입 횟수. 품질 하락을 비용 감소로 상쇄하지 않는다. |
| 시간·반복 | 전체 경과 시간, 재시도·취소·미완료, 실패 후 재시작, 중복 spawn, 명령·리뷰 횟수. 실패 시도도 비용에 포함한다. |
| 보고된 사용량 | input/output/cached input과 보고 비율, requested model별 합계. cached input은 input의 일부이며 중복 합산하지 않는다. |
| harness overhead | 부모의 지시·결과 전달, 반복 polling, prompt/schema 준비, 요약·재구성, 로컬 검증 비용을 별도로 기록한다. 누락은 `unknown`이다. |
| 성공당 비용 | 같은 workload의 전체 시도 비용을 성공 수로 나눈다. 성공 0이면 유한한 개선값을 보고하지 않는다. USD 청구자료가 없으면 금액은 `unknown`이다. |

현재 Hwahap `cost.rs`는 요청·완료·중단·미완료와 보고 토큰을 집계한다. 부모 전달 토큰과 전체 USD 청구금액은 모른다.
KiroCrew의 기본 task token budget도 0(무제한)이며 `tokens_used`는 출력 문자열 길이로 증가하는 경로가 있다.
`subagent_cost`의 측정값은 CPU·메모리이므로 LLM 청구 비용과 다르다. [상수][kc-limits], [계수][kc-tokens], [자원 측정][kc-cost]
따라서 이번 설계 비교는 비용 절감의 증거가 아니다. 같은 성공 조건·전체 실패 비용·usage 누락률이 있는 비교 결과가 필요하다.

[rob]: https://www.cs.unc.edu/~stotts/COMP590-059-f24/robsrules.html
[sqlite]: https://www.sqlite.org/testing.html
[sqlite-coverage]: https://www.sqlite.org/testing.html
[uber]: https://www.uber.com/us/en/blog/efficient-software-factory/
[codex]: https://learn.chatgpt.com/docs/agent-configuration/subagents
[kc]: https://github.com/kirodotdev/KiroCrew/tree/5f5e3dec480571f35dc72da06213ac8983ffc0af
[kc-terminal]: https://github.com/kirodotdev/KiroCrew/blob/5f5e3dec480571f35dc72da06213ac8983ffc0af/src/kiro_crew/subagent_manager/terminal.py#L35-L109
[kc-race]: https://github.com/kirodotdev/KiroCrew/blob/5f5e3dec480571f35dc72da06213ac8983ffc0af/test/test_subagent_reap_race.py#L216-L265
[kc-continue]: https://github.com/kirodotdev/KiroCrew/blob/5f5e3dec480571f35dc72da06213ac8983ffc0af/src/kiro_crew/subagent_manager/continuation.py#L246-L397
[kc-meta]: https://github.com/kirodotdev/KiroCrew/blob/5f5e3dec480571f35dc72da06213ac8983ffc0af/src/kiro_crew/subagent_completion_meta.py#L30-L85
[kc-snapshot]: https://github.com/kirodotdev/KiroCrew/blob/5f5e3dec480571f35dc72da06213ac8983ffc0af/src/kiro_crew/taskrunner.py#L1872-L1963
[kc-prompt]: https://github.com/kirodotdev/KiroCrew/blob/5f5e3dec480571f35dc72da06213ac8983ffc0af/src/kiro_crew/task_executor.py#L730-L805
[kc-session]: https://github.com/kirodotdev/KiroCrew/blob/5f5e3dec480571f35dc72da06213ac8983ffc0af/src/kiro_crew/session_allocation.py#L532-L576
[kc-checkpoint]: https://github.com/kirodotdev/KiroCrew/blob/5f5e3dec480571f35dc72da06213ac8983ffc0af/src/kiro_crew/task_reporter.py#L155-L185
[kc-review]: https://github.com/kirodotdev/KiroCrew/blob/5f5e3dec480571f35dc72da06213ac8983ffc0af/src/kiro_crew/task_executor.py#L867-L943
[kc-git]: https://github.com/kirodotdev/KiroCrew/blob/5f5e3dec480571f35dc72da06213ac8983ffc0af/src/kiro_crew/git_coord.py#L55-L118
[kc-lessons]: https://github.com/kirodotdev/KiroCrew/blob/5f5e3dec480571f35dc72da06213ac8983ffc0af/src/kiro_crew/taskrunner.py#L1677-L1727
[kc-limits]: https://github.com/kirodotdev/KiroCrew/blob/5f5e3dec480571f35dc72da06213ac8983ffc0af/src/kiro_crew/task_models.py#L9-L18
[kc-tokens]: https://github.com/kirodotdev/KiroCrew/blob/5f5e3dec480571f35dc72da06213ac8983ffc0af/src/kiro_crew/task_executor.py#L357-L366
[kc-cost]: https://github.com/kirodotdev/KiroCrew/blob/5f5e3dec480571f35dc72da06213ac8983ffc0af/src/kiro_crew/subagent_cost.py#L42-L51
