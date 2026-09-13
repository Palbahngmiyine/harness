# 오늘의 대화 기록 찾기

호출한 앱과 기록의 출처를 구분한다. **Codex에서 호출해도 Claude Code 기록을, Claude Code에서 호출해도 Codex 기록을 각각 찾는다.** 전용 조회 도구가 지원하는 출처에만 그 도구를 먼저 쓰고 나머지는 로컬 파일에서 확인한다. 양쪽 확인이 끝나거나 각 접근 한계가 확인되기 전에는 조회를 끝내지 않는다.

이 문서는 Claude Code 2.1 계열과 Codex CLI 0.153 계열의 로컬 기록 형식을 다룬다. 공식적으로 고정된 저장 API가 아니므로 실행 때 파일·컬럼·이벤트 종류를 확인한다. 아래는 필요한 조회 한 줄을 고르는 참고 문서이며 설치할 실행기나 순서대로 돌릴 스크립트가 아니다.

## 공통 규칙

- 사용자 범위: 현재 OS 사용자의 홈과 알려진 저장 위치만 쓴다. Codex 루트는 `CODEX_HOME` 또는 `~/.codex`, Claude Code 루트는 `CLAUDE_CONFIG_DIR` 또는 `~/.claude`다. 현재 프로젝트 경로로 세션을 제한하지 않는다. 다른 사용자의 홈·백업·원격 계정을 탐색하지 않는다.
- 날짜: 사용자 시간대의 대상일 00:00부터 다음 날 00:00 전까지를 UTC로 바꾼 반열린 구간으로 필터한다. KST의 D일은 `[D-1일 15:00:00Z, D일 15:00:00Z)`다. 끝 시각은 호출 시작에 고정한 조회 시각을 넘지 않게 잘라 오늘은 그 시각까지의 진행만 읽는다. 시작이 끝 이상이면 읽을 활동 구간이 없다. 다른 시간대·서머타임에는 고정 `+9 hours`를 쓰지 않는다.
- 후보와 활동: 파일 mtime·작업의 갱신 시각은 후보 단서다. 대상일 이후에도 갱신된 세션을 놓치지 않도록 **후보 갱신 시각에 대상일 끝의 상한을 두지 않는다.** 후보를 고른 뒤 메시지·이벤트 자체의 시각으로 대상일 활동을 판정한다. 파일의 시작일 폴더만으로 오늘 활동을 찾지 않는다.
- 시각 단위: Claude history와 Codex `*_ms`는 epoch 밀리초, Codex `created_at` 등은 epoch 초, JSONL 이벤트는 보통 ISO 8601이다. 단위·시간대·소수 초를 정규화한다. 문자열 비교는 UTC와 소수 초 자릿수가 같은 경우에만 한다.
- 읽기 전용: SQLite는 `file:<절대경로>?mode=ro`로 열고 스키마를 확인한다. WAL 접근 등으로 실패하면 원본 JSONL을 우선한다. `immutable=1`은 쓰기 중인 DB의 최신 WAL을 반영하지 못할 수 있으므로 일상적인 재시도 기본값으로 쓰지 않는다. 불가피하게 사용한 경우 `일부 확인·최근 변경 누락 가능`으로 남기며 빈 결과를 활동 없음으로 판단하지 않는다.
- 출력: 먼저 메타데이터로 후보를 좁히고 시각·출처·종류·짧은 발췌를 읽는다. 필요한 요청·정정·결과 문맥만 추가로 읽는다. 추론 내용(`thinking`·`reasoning`), 시스템 주입, 인증 정보, 원문 전체를 출력하거나 별도 저장하지 않는다. 도구 결과는 필요한 실행 증거만 읽는다.
- 실패: 도구가 없거나 형식·권한이 맞지 않으면 그 출처의 대체 읽기 경로를 확인한다. 한쪽 실패로 다른 쪽의 조회를 중단하지 않는다. 모든 경로가 막혔으면 출처별 한계를 알리고 사용자 제공 내용으로 문답을 이어 간다.

예시 변수의 `CODEX_ROOT`·`CLAUDE_ROOT`·`STATE_DB`·`HISTORY_DB`·`SESSION_FILE`·`ROLLOUT_FILE`에는 확인한 경로를, `SESSION_ID`에는 확인한 세션 ID를 넣는다. `FROM_MS`·`TO_MS`에는 조회 시각으로 제한한 대상일 구간을 넣고, 사용자 경로와 검색값은 안전하게 인용한다. 파일명 접미사는 디렉터리에서 확인하고 선택한 DB에 필요한 테이블이 있는지 먼저 본다.

## Codex

`list_threads`·`read_thread`가 있으면 로컬 Codex 후보와 내용을 먼저 확인한다. 도구의 출처·host·페이지·요약 한계를 확인한다. 이 목록은 Claude Code 로그를 대신하지 않으며, 다른 출처의 ChatGPT 대화를 Codex 활동으로 세지 않는다. 정확한 당일 내용이 요약에 없거나 목록이 불완전하면 다음 로컬 자료로 보완한다.

| 위치 | 용도와 확인할 것 |
|---|---|
| `$CODEX_ROOT/state_*.sqlite`의 `threads` | 후보 색인. `id`, `rollout_path`, `created_at_ms`, `updated_at_ms`, `thread_source`, `source`, `archived` 등 실제 컬럼 확인. 오래된 스키마는 초 단위 컬럼일 수 있다 |
| `$CODEX_ROOT/thread_history_*.sqlite`의 `thread_items` | 존재하면 `thread_id`, `item_type`, `created_at_ms`, `item_json`으로 필요한 구간 조회. 없거나 최근 항목이 지연되면 rollout 사용 |
| 색인의 `rollout_path` | JSONL 원본. `sessions/`뿐 아니라 `archived_sessions/`에 있을 수 있다. 시작일 경로와 실제 활동일은 다를 수 있다 |
| `session_index.jsonl`, `history.jsonl` | 존재와 최신성을 확인한 경우 후보 보조로 사용. 한 설치본에서 오래됐다고 모든 환경에서 제외하지 않는다. history의 사용자 입력만으로 결과를 판정하지 않는다 |

`thread_source='user'`만 허용하는 필터는 쓰지 않는다. null인 구형 기록, 음성·이관된 작업, 자율 작업에도 사용자와 관련된 활동이 있을 수 있다. `guardian_review`·`subagent`는 독립 사용자 사건에서 제외하고 필요하면 부모의 실행 근거로만 연결한다. `automation` 등은 사용자 직접 발화와 구분한다. 모호한 출처는 메타데이터와 본문으로 확인하고 사람의 입력으로 추정하지 않는다.

필요한 읽기 예시:

- 스키마: `sqlite3 "file:$STATE_DB?mode=ro" 'PRAGMA table_info(threads);'`
- ms 컬럼이 있는 색인의 후보: `sqlite3 "file:$STATE_DB?mode=ro" "SELECT id, thread_source, rollout_path FROM threads WHERE updated_at_ms >= $FROM_MS AND created_at_ms < $TO_MS AND coalesce(thread_source,'') NOT IN ('guardian_review','subagent') ORDER BY updated_at_ms DESC LIMIT 30;"` 제한에 걸리면 페이지를 이어 보거나 표본임을 밝힌다. archived 여부만으로 제외하지 않는다.
- 항목 종류와 수: `sqlite3 "file:$HISTORY_DB?mode=ro" "SELECT thread_id, item_type, count(*) FROM thread_items WHERE created_at_ms >= $FROM_MS AND created_at_ms < $TO_MS GROUP BY thread_id, item_type;"` 항목 생성 시각의 보조 조회다. 이전에 생성되어 오늘 완료·갱신된 항목은 빠질 수 있으므로 이 결과만으로 당일 활동을 확정하거나 제외하지 않는다. 대상 후보 ID와 대조하고 필요한 발화·보고·원본 이벤트를 읽는다.
- JSONL 형식 확인: `head -n 8 "$ROLLOUT_FILE" | jq -c '{type, payload_type: .payload.type, item_type: .payload.item.type}'` 본문이 아닌 구조만 본다. 앞부분이 메타데이터뿐이면 필요한 이벤트 종류를 좁혀 더 확인한다.

| 항목·이벤트 | 취급 |
|---|---|
| SQLite `userMessage`의 `content` 중 text | 사용자 입력. 배열의 모든 text 조각을 읽고 도구 결과·주입 여부 확인 |
| SQLite `agentMessage`의 `text` | 에이전트의 진행·결과 보고. 완료 사실과 구분 |
| SQLite `commandExecution`·`fileChange` | 필요할 때 실행 상태·exit code·변경 내용을 확인. 명령 문자열만 있는 것은 성공 증거가 아님 |
| JSONL `event_msg`의 `user_message`·`agent_message` | 해당 버전에서 확인한 `message` 등 본문 필드 사용 |
| JSONL `event_msg`의 `item_completed` | 실제 `payload.item.type`을 확인. `UserMessage`·`AgentMessage` 등의 본문 구조를 확인해서 읽음. `started_at_ms`·`completed_at_ms`가 있으면 이벤트 시각과 대조하고, 시작과 완료를 구분 |
| JSONL `response_item`의 user·assistant | 시스템 주입·복제된 대화·다른 이벤트와 중복될 수 있음. 유일한 자료일 때 실제 사용자 입력 여부를 확인하고 불명확하면 보류 |

SQLite와 JSONL의 같은 항목을 중복 집계하지 않는다. JSONL의 세션·부모·항목 ID와 실제 이벤트 시각을 확인한다. 재생·이관으로 시각이 고정된 로그는 대상일의 실제 활동 근거로 확정하지 않는다. SQLite에서 사용자 입력이 0건이거나 최근 결과가 빠졌으면 에이전트 항목과 원본 이벤트도 확인한다.

색인이 없으면 알려진 세션 저장 루트의 파일명·mtime으로 후보를 찾되 본문 전체를 재귀 검색하지 않는다. 예: `find "$CODEX_ROOT/sessions" -type f -name '*.jsonl' -newermt '<대상일 시작 시각>'`는 후보 조회이며 날짜 판정은 이벤트에서 한다. 존재하는 `archived_sessions`도 같은 방식으로 확인한다. 환경이 이 옵션을 지원하지 않으면 제공된 파일 메타데이터 도구를 쓴다. 제한·누락 가능성을 밝힌다.

## Claude Code

Claude Code를 직접 실행 중이지 않아도 기록이 있으면 읽을 수 있다. CLI 실행 파일이 없다는 이유만으로 기록 없음으로 판단하지 않는다. 로컬 Claude Code 기록의 조회이며 Claude 웹·Desktop의 모든 대화까지 읽었다고 말하지 않는다.

| 위치 | 용도와 확인할 것 |
|---|---|
| `$CLAUDE_ROOT/history.jsonl` | `timestamp`(ms), `sessionId`, `project`, `display`로 대상일의 입력과 세션 후보 확인. 사용자 입력 색인이며 모든 자율 실행을 포함하지는 않음 |
| `$CLAUDE_ROOT/projects/*/<sessionId>.jsonl` | 세션 본문. 프로젝트 슬러그 변환을 추측하지 말고 확인한 ID로 파일을 찾음. worktree는 다른 프로젝트 디렉터리일 수 있음 |
| `projects/*/sessions-index.json` | 존재하고 최신이면 후보 보조. 없어도 세션 본문 조회 가능 |
| `<sessionId>/subagents/`, `tool-results/`, `memory/` 등 | 보조 자료. 독립 사용자 사건에서 제외. 부모 결과의 근거가 필요할 때만 관련 부분 확인 |

history에서 후보를 고른 후 프로젝트별 최상위 세션 파일의 mtime도 확인해 **입력 없이 이어진 세션**을 보완한다. 예: `find "$CLAUDE_ROOT/projects" -mindepth 2 -maxdepth 2 -type f -name '*.jsonl' -newermt '<대상일 시작 시각>'`. 광범위한 원문 검색이나 subagents 재귀 조회 없이 후보를 좁히고, 실제 날짜는 각 줄의 timestamp로 판정한다.

필요한 읽기 예시:

- history 후보: `jq -c --argjson f "$FROM_MS" --argjson t "$TO_MS" 'select(.timestamp >= $f and .timestamp < $t) | {timestamp, sessionId, project}' "$CLAUDE_ROOT/history.jsonl"`
- 확인한 ID의 본문 위치: `ls "$CLAUDE_ROOT"/projects/*/"$SESSION_ID".jsonl`
- 형식: `head -n 5 "$SESSION_FILE" | jq -c '{type, promptSource, isMeta, isSidechain, content_type: (.message.content | type)}'`

| 기록 조건 | 취급 |
|---|---|
| `type=user`, `promptSource=typed` | 직접 입력 후보. `isMeta`, `isSidechain`, `toolUseResult`, content의 `tool_result`·주입 여부를 함께 확인 |
| `type=user`, `promptSource` 없음 | 구형 형식일 수 있음. 무조건 제외하지 말고 history의 세션·시각·본문과 대조. 불명확하면 `사용자 입력 여부 미확인` |
| `type=user`에 `toolUseResult` 또는 `message.content[].type=tool_result` | 도구 결과. 사용자 발화가 아님 |
| `isMeta=true`, `isSidechain=true`, 시스템·attachment | 메타·서브에이전트·주입. 사용자 발화와 분리 |
| `type=assistant`의 `message.content[]` 중 `type=text` | 진행·결과 보고. `thinking`은 제외, `tool_use`만으로 실행 성공을 주장하지 않음 |
| `ai-title`, `summary` 등 | 제목·요약 단서. 실제 사건 날짜와 결과는 본문에서 확인 |

content는 문자열 또는 배열일 수 있다. slash command 자체는 성과가 아니지만, 뒤에 이어진 실제 작업 요청과 결과까지 버리지 않는다. 중복 이벤트는 UUID·부모 관계로 줄인다. 보존 기간·설정·삭제에 따라 남은 기록이 다르므로 일정 기간 이전은 항상 없다고 단정하지 않는다.

## 여러 날 이어지는 작업의 당일 진행

goal 자동 계속·긴 단일 턴·재개된 세션 모두에 적용한다. 오늘 새 사용자 메시지가 없거나 아직 최종 답변이 없어도 조회한다. 사용자가 지정한 작업과 확인된 진행 중 작업은 목록·색인의 갱신 지연으로 빠질 수 있으므로, 알려진 원본 경로도 확인한다. 활동 중 표시 자체는 오늘 작업을 했다는 근거가 아니다.

1. **당일 이벤트:** 대상일 구간의 진행 보고·실행 결과·파일 변경을 읽는다. 전용 도구가 `inProgress`인 턴에 빈 `items`를 반환하거나 요약이 전날에서 끝나면 원본으로 보완한다. 턴 시작 시각·SQLite 항목 생성 시각만 필터하지 않는다. 자정 전 시작해 오늘 끝난 실행은 `오늘 완료 확인`으로 기록하고 전체 실행량을 오늘 수행량으로 돌리지 않는다. 진행 중 명령은 시작만 확인됐으면 `실행 중·결과 미확인`이다.
2. **이전 상태와 당일 변화:** 고른 사건에 필요한 직전 상태·원래 의도만 날짜를 붙여 읽고 `이전까지 / 오늘 새로 확인한 변경·실패·검증 / 조회 시각의 남은 일`로 나눈다. 직전 상태를 못 읽으면 `이전 상태 미확인`으로 두고 변경량을 추정하지 않는다. 오늘 생성된 요약·컴팩션에 적힌 누적 성과를 모두 오늘 일로 옮기지 않는다. 같은 항목의 중복·후속 갱신은 하나로 연결한다.
3. **완료 범위:** 턴의 최종 답변이나 `task_complete`는 전체 goal 완료의 증거가 아니다. 부분 구현·해당 검사 통과·통합 미확인·전체 목표 진행 중을 구분한다. 검증 결과에는 대상과 범위를 붙이고 재시도 중인 실패도 숨기지 않는다. 종료 선언이 없다는 이유로 확인한 당일 변화까지 누락하지 않는다.
4. **학습으로 연결:** 오늘 변화 중 하나의 `구체적 입력 / 바뀐 처리·규칙 / 관찰된 출력 / 근거 위치와 한계`를 확보해 문답에 넘긴다. 원리 판단에 보고만으로 부족하면 관련 코드·문서·이미 남은 실행 결과의 작은 구간을 읽는다. 오늘 변화 근거가 없으면 그 한계를 밝히고 이전 작업을 오늘 새 성과처럼 제시하지 않는다.

조회 기준 시각 이후의 변경은 이번 기록에서 제외하고 다음 호출에서 확인한다. 일기 때문에 작업 완료를 기다리거나 목표·작업 상태를 바꾸거나 다른 작업에 메시지를 보내지 않는다. 원문·작업 식별자는 허용된 개인 일기의 근거에 필요한 만큼만 쓰며 배포 스킬·공개 PR·테스트 예제에는 복제하지 않는다.

## 양쪽 기록을 사건과 상태로 연결한다

- 출처마다 조회 창·읽은 범위·접근 결과를 남긴 뒤 최대 세 사건을 소개한다. 부모·자식, resume·fork, 현재 대화의 복제, 두 도구 사이에서 이어 한 작업을 근거·내용으로 대조한다. 제목만 같다고 합치거나 도구가 다르다고 별도 성과로 세지 않는다.
- 사용자 발화가 0건이어도 에이전트의 진행·실행·결과를 확인한다. `사용자 발화 없이 에이전트가 자율 실행`으로 표시하고 사용자가 결과를 확인했는지는 문답에서 묻는다. 기록 없음과 활동 없음도 구분한다.
- 상태는 읽은 범위의 `요청 / 진행 중 / 완료 보고 / 실행 근거 확인 / 실패·중단 / 미확인` 등으로 적는다. 과거 로그는 그 시점의 근거다. 현재 완료 여부까지 알 수 없으면 시점을 붙인다. 계획·보고·실제 결과가 충돌하면 그대로 표시한다.
- `사용자 의도 / LLM의 당일 변화·조회 시각·현재 상태 / 확인 근거·남은 확인 / 사용자 설명 확인 범위 / 다음 확인`을 `SKILL.md`의 문답과 일기에 이어 쓴다. 소개만 하고 버리거나 전체 대화 원문을 옮기지 않는다. 사용자가 확인하지 않은 이해·감정·직접 수행을 채우지 않는다.

## 변경 시 확인할 행동

Codex 조회 도구만 있는 환경에서 Claude 파일까지 읽는지, 양쪽 실행 환경을 바꿔도 같은 출처를 확인하는지, 사용자별 저장 루트 변경, 늦게 갱신된 옛 세션, 자정 경계, 구형·null 출처, archived 기록, 입력 없는 자율 실행, WAL·권한 실패, JSONL 형식 차이를 확인한다. 장기 goal은 전날 시작한 같은 턴의 오늘 결과, 빈 전용 조회 본문, 자정을 넘긴 실행, 오늘 활동이 없는 진행 중 작업, 호출 이후 이벤트 제외, 부분 완료와 전체 목표 구분을 확인한다. 실제 소량 조회와 형식 검토의 범위를 구분하고 전체 하루를 읽었다고 과장하지 않는다.
