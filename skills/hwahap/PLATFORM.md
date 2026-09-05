# Native 실행의 플랫폼 근거와 검증 범위

2026-09-05의 현재 소스와 자동 테스트를 기준으로 작성했다. 실제 호스트의 도구 제공 여부와
모델 적용·권한·청구 사용량은 각각 확인해야 하며, 요청 기록만으로 검증됐다고 판단하지 않는다.

## 1. Codex 기본 하위 에이전트

[OpenAI 공식 문서](https://learn.chatgpt.com/docs/agent-configuration/subagents)는 Codex가
하위 에이전트 생성·대기·중단을 관리하고, 하위 에이전트가 부모의 현재 권한 정책을 상속한다고 설명한다.
Hwahap은 호스트에 노출된 native 도구를 사용하며 MCP 서버 자체가 모델 세션을 시작하지 않는다.

현재 호스트의 `spawn_agent` 호출에는 `task_name`, `message`, `fork_turns`, `model`,
`reasoning_effort`가 있다. 별도 `cwd`·`sandbox` 인수는 없다. Hwahap은 `fork_turns=none`과
요청된 모델·effort를 전달하도록 요구하며 절대 작업 경로와 접근 범위는 지시에 포함한다.
따라서 read-only 지침과 Git 사후 검사는 OS 격리의 증거가 아니다. 공식 문서의 custom agent
설정 기능도 이 구현이 개별 spawn의 샌드박스를 검증했다는 뜻은 아니다.

실행 증거는 [native 모듈](runtime/src/native.rs)과
[MCP instructions](runtime/src/mcp.rs)에 정의되어 있다.
요청 모델은 실제 적용 모델과 구분하며, 도구가 없는 호스트에서는 실행 한계를 보고한다.
호스트가 Astra인 경우에도 `Recommender`·`PlanSynthesis`만 coordinator 처리가 허용된다.
최종 리뷰와 그 밖의 독립 역할은 새 하위 에이전트가 수행한다.

공식 문서는 플랫폼 기능의 근거이며, 이 저장소의 기본 프로필은
[profile.rs](runtime/src/profile.rs)가 정의한다. Deep은 `gpt-6-astra` / `high`,
Economy는 Luna / `medium`, Critic은 Terra / `high`다.

## 2. 저장과 중단 복구

[호스트 실행기](runtime/src/native/host.rs)는 저장소당 한 실행을 관리하고 OS 파일 잠금으로 다른
MCP 프로세스의 동시 실행을 거부한다. `status`는 진행 상황을 읽으며 새 에이전트를 만들지 않는다.

| 기록 | 의미 |
|---|---|
| `native-request-<id>.json` | 호스트에 전달하기 전에 저장한 실행 요청 |
| `native-pending.json` | 현재 요청과 등록된 agent ID, 완료 상태 |
| `native-completion-<id>.json` | 호스트가 전달한 종료 결과와 선택적 사용량 |
| `native-stopped-<id>.json` | 호스트가 남은 에이전트와 명령의 종료를 확인한 기록 |
| `receipt-<sequence>-<role>.json` | 실행 증거의 출처가 명시된 세션 결과 |

호스트는 생성 직후 agent ID를 등록하고, 동일 요청에 두 번째 에이전트를 만들지 않는다.
완료는 등록된 ID와 일치해야 하며 같은 내용의 재전송은 한 번만 소비한다. 다른 완료 내용은 거부한다.
생성 후 등록 전에 끊겼다면 호스트는 해당 요청으로 만든 에이전트가 있는지 찾아 종료해야 한다.
종료 여부가 불명확할 때 `all_work_stopped=true`를 보내면 안 된다.

기본 한도는 실행당 native 요청 64회, 요청당 대기 900초다. 재시도 요청도 한도에 포함된다.
재시작과 시간 초과는 `native_stop`을 요구한다. 이는 실제 종료를 자동 수행했다는 뜻이 아니다.
[config.rs](runtime/src/config.rs), [broker](runtime/src/native/broker.rs),
[native_surface.rs](runtime/tests/native_surface.rs)가 설정과 복구 검사의 근거다.

## 3. 현재 확인한 것과 남은 검증

자동 테스트는 실제 임시 Git 저장소와 통제한 에이전트 결과를 사용한다.

- 단위 테스트: 모델·역할 배정, 상태 저장, JSON 계약, 사용량 오류와 집계.
- 사이클 테스트: Luna 첫 구현 뒤 Astra 재작업 한 번, 검증·검토·commit·ship 조건.
- native 인터페이스 테스트: 등록·완료 연결, 중복 완료, 재시작 복구, 시간 초과와 잠금.
- MCP 인터페이스 테스트: 세 도구의 공개 계약과 입력 검증.

2026-09-05의 제한된 실제 호스트 canary에서는 Luna `fact_finder` 하위 에이전트를 생성하고,
등록한 뒤 반환된 JSON을 completion으로 전달했다. 이어 현재 Astra가 `recommender`를
`coordinator`로 등록·처리했고, 실행은 `deciding / await_user`까지 진행했다. 요청 2개, 완료 2개
(하위 에이전트 1개·coordinator 1개), 미완료 0개, 사용량 보고 0개가 기록됐다. 두 native receipt와
pending 제거를 확인했으며 EOF로 MCP가 종료됐다. 실제 사용 토큰이나 청구금액은 확인하지 못했다.
초기 canary에서 발견한 자체 상태 파일 변경 오탐은 수정하고 `.gitignore` 없는 저장소에서 재검증했다.
이 관찰은 전체 계획·구현·최종 검토·PR 생성의 성공 증거가 아니다.

다음은 별도 실제 실행으로 검증해야 한다.

- 계획 합성·구현·독립 Astra 최종 검토·PR 생성을 포함하는 전체 실제 모델 실행.
- 호스트 연결 해제·실제 하위 에이전트 중단 이후 남은 명령의 종료와 복구.
- 각 배포 환경에서 MCP 연결, 하위 에이전트 도구 및 요청 모델·effort의 제공 여부.
- 같은 성공 조건에서 기존 구성과 비교한 성공률·소요시간·사용량·사용자 개입.

## 4. 설치와 실행 환경

설치는 [README.md](README.md)의 로컬 MCP 등록과 스킬 복사 절차를 따른다.
[bin/hwahap](bin/hwahap)은 빌드된 바이너리를 찾아 실행하며, 진단은 stderr에 쓰고
stdout은 MCP 전송에 사용한다. 이 구현은 스킬 디렉터리 배치를 유지하며 별도 플러그인 패키징에
의존하지 않는다.

테스트 명령은 POSIX `sh -c`로 실행하고 native 실행 잠금은 Unix `flock`을 사용한다.
Windows 네이티브 실행은 지원을 확인하지 않았으며 현재 잠금 구현이 거부한다.
호스트의 권한 정책과 실제 작업 경로 접근 가능 여부도 배포 환경에서 확인해야 한다.

## 5. 사용량과 비용의 의미

[cost.rs](runtime/src/cost.rs)는 현재 실행의 요청·완료 artifacts를 집계하며 receipt를 다시 더하지
않는다. 재시도·미완료·중단 요청도 포함한다. requested model별 토큰 소계와 coordinator·하위
에이전트의 사용량 보고 비율은 호스트가 제공한 계수에 근거한다. 실제 적용 모델은 독립 검증하지 않는다.

누락된 사용량은 0이 아니라 `unknown`이다. coordinator가 보고한 작업 사용량과 부모의 결과 전달
토큰도 구분하며, 후자는 계측하지 않는다. 따라서 전체 청구금액은 `unknown`이다. 요청 수 감소나
모델 교체만으로 실제 비용 절감을 단정하지 않는다. 손상된 JSON, cached input이 total input보다
큰 값, 정수 overflow는 명시적 오류로 처리한다.
