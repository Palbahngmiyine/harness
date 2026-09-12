# 오늘의 대화 기록 찾기

확인일: 2026-09-11. Claude Code 2.1.268과 Codex CLI 0.153.4가 macOS의 한 사용자 홈에 남긴 파일을 직접 읽어 확인했다. 두 도구의 공식 문서가 보장하는 형식이 아니므로 업데이트 뒤 파일명·테이블·필드가 달라질 수 있다.

`SKILL.md` 1절에서 오늘의 대화 기록을 처음 찾을 때 이 문서의 공통 규칙과 해당 도구의 절만 읽는다. 두 도구를 모두 확인하면 "두 도구의 기록을 합칠 때" 절도, 사용자 발화가 0건이면 "사용자 발화가 없는 날" 절도 읽는다. 아래 조회 예시는 읽기 전용 참고 예시다. `jq`·`sqlite3` 같은 도구가 없거나 파일 읽기 권한이 없으면 예시를 생략하고 `SKILL.md`의 “현재 대화만 확인했습니다” 흐름으로 돌아간다. 예시를 순서대로 실행하는 절차로 다루지 않고 필요한 한 줄만 고른다. 예시의 `$FROM_MS`·`$TO_MS`·`$FROM_ISO`·`$TO_ISO`·`$FILE`·`$ROLLOUT`는 값이 들어갈 자리다. `$STATE_DB`·`$HISTORY_DB`는 `ls -1t ~/.codex/state_*.sqlite | head -1`과 `ls -1t ~/.codex/thread_history_*.sqlite | head -1`로 먼저 확인한 절대경로다. `file:` URI 안에서는 `~`가 확장되지 않고 `$(...)`는 실행 환경이 거부할 수 있으므로 절대경로를 넣는다.

## 공통 규칙

- 하루 창: 사용자 시간대의 00:00부터 다음 날 00:00 전까지를 UTC로 바꿔 필터한다. KST(UTC+9)의 D일은 `[D-1일 15:00:00Z, D일 15:00:00Z)`다. epoch 밀리초는 `jq -n '"2026-09-10T15:00:00Z"|fromdateiso8601*1000'`처럼 구한다. 예시의 `+32400`과 `'+9 hours'`는 KST 오프셋이며 사용자 시간대에 맞춰 바꾼다.
- 시각 표기 세 가지: Claude Code 트랜스크립트는 UTC ISO 8601 문자열(밀리초 포함, 예 `2026-09-11T03:04:05.678Z`)이라 같은 형식의 문자열끼리 비교한다. `~/.claude/history.jsonl`과 Codex의 `*_ms` 컬럼은 epoch 밀리초다. Codex의 `created_at`과 `thread_turns.started_at`은 epoch 초다. 비교 전에 단위를 맞춘다.
- 읽기 전용: 파일은 읽기만 한다. SQLite는 `file:<경로>?mode=ro` URI로 열고, 열기에 실패하면 `&immutable=1`을 덧붙인다. 플래그 없이 열지 않는다. `immutable=1`은 WAL(write-ahead log, 아직 본 파일에 합쳐지지 않은 최근 변경 기록)을 무시하므로 도구가 쓰는 중이면 최근 몇 분이 빠질 수 있다.
- 파일명의 버전 접미사(`state_5`, `thread_history_1`)는 하드코딩하지 않고 `ls -1t ~/.codex/state_*.sqlite | head -1`처럼 최신 파일을 고른다.
- 출력은 시각·제목·앞 100자 정도로 제한한다(`gsub("\\s+";" ")|.[0:100]`, `substr(...,1,100)`). 원문 전체를 대화나 일기로 옮기지 않는다. 도구 결과·시스템 주입·서브에이전트 대화는 사용자 발화가 아니다.

## Claude Code

| 경로 | 내용 | 비고 |
|---|---|---|
| `~/.claude/history.jsonl` | 전역 프롬프트 히스토리. 한 줄이 한 입력이며 `display`(사용자 원문), `project`(작업 디렉터리 절대경로), `sessionId`, `timestamp`(epoch ms) | 오늘 세션을 나열하는 1차 소스. `display`가 `/`로 시작하면 슬래시 명령이며 사건이 아니다. 지금 진행 중인 세션도 여기에 나타나므로 현재 대화와 한 사건으로 다룬다 |
| `~/.claude/projects/<슬러그>/<sessionId>.jsonl` | 세션 트랜스크립트. 슬러그는 작업 디렉터리 절대경로의 `/`, `.`, `@`를 `-`로 바꾼 것 | git worktree는 별도 슬러그 디렉터리에 저장되므로 `sessionId`로 전체 프로젝트를 glob한다 |
| `<sessionId>/subagents/agent-*.jsonl` | 서브에이전트 대화(`isSidechain: true`) | 사용자 발화 없음. 기본 제외 |
| `<sessionId>/tool-results/`, `.meta.json`, `~/.claude/projects/*/memory/` | 도구 결과·부속·메모리 | 대화 아님 |

트랜스크립트 한 줄의 `type`으로 발화를 구분한다.

| `type`과 조건 | 뜻 | 취급 |
|---|---|---|
| `user`이고 `promptSource == "typed"` | 사용자가 직접 입력한 프롬프트. `message.content`는 보통 문자열, 첨부가 있으면 배열 | 사용자 발화 |
| `user`이고 `toolUseResult`가 있음(`promptSource` 없음) | 도구 실행 결과 | 제외 |
| `user`이고 `isMeta: true` | 슬래시 명령 부속 | 제외 |
| `assistant`이고 `isSidechain`이 아님 | 에이전트 답변. `message.content[]`는 `text`·`thinking`·`tool_use` 중 한 종류 | 결과 보고 근거 |
| `ai-title` | 자동 생성 제목(`aiTitle`) | 제목 단서 |
| `attachment`, `system`, `last-prompt`, `cost-state` 등 | 시스템 주입·상태 | 제외 |

예시(읽기 전용):

- 오늘 입력한 프롬프트 목록(시각·세션·프로젝트·앞 100자): `jq -r --argjson f "$FROM_MS" --argjson t "$TO_MS" 'select(.timestamp>=$f and .timestamp<$t)|[(.timestamp/1000+32400|strftime("%H:%M")), .sessionId[0:8], (.project|split("/")|last), (.display|gsub("\\s+";" ")|.[0:100])]|@tsv' ~/.claude/history.jsonl`
- 세션 파일 찾기: `ls ~/.claude/projects/*/<sessionId>.jsonl`. 수정 시각으로 후보를 볼 때는 `find ~/.claude/projects -name '*.jsonl' -newermt '<대상일>' -not -path '*/subagents/*'`(대상일 이후에도 이어진 세션이 빠지지 않도록 상한을 두지 않는다). 수정 시각은 단서이며 날짜 판정은 아래 예시의 `timestamp`로 한다.
- 세션 파일의 오늘 사용자 프롬프트: `jq -r --arg f "$FROM_ISO" --arg t "$TO_ISO" 'select(.type=="user" and .promptSource=="typed" and .timestamp>=$f and .timestamp<$t)|[(.timestamp[0:19]+"Z"|fromdateiso8601+32400|strftime("%H:%M")), ((.message.content|if type=="string" then . else map(.text//"")|join(" ") end)|gsub("\\s+";" ")|.[0:100])]|@tsv' "$FILE"`
- 세션 파일의 오늘 assistant 답변(시각·앞 100자): `jq -r --arg f "$FROM_ISO" --arg t "$TO_ISO" 'select(.type=="assistant" and (.isSidechain|not) and .timestamp>=$f and .timestamp<$t)|.timestamp as $ts|.message.content[]|select(.type=="text")|[($ts[0:19]+"Z"|fromdateiso8601+32400|strftime("%H:%M")), (.text|gsub("\\s+";" ")|.[0:100])]|@tsv' "$FILE"`
- 세션 제목: `jq -r 'select(.type=="ai-title")|.aiTitle' "$FILE" | tail -1`

한계: 트랜스크립트 보존 기본값은 30일이라(`cleanupPeriodDays` 미설정 시) 한 달 넘은 날짜는 조회할 수 없다고 안내한다. `timestamp`에 밀리초가 있으므로 `fromdateiso8601` 앞에서 `[0:19]+"Z"`로 자른다. 파일 하나는 수 MB 수준이라 통째로 `jq`에 넘겨도 된다.

## Codex CLI

| 경로 | 내용 | 비고 |
|---|---|---|
| `~/.codex/state_*.sqlite`의 `threads` | 스레드 목록. `id`(UUID), `thread_source`(`user`·`guardian_review`·`subagent`), `cwd`, `title`, `updated_at_ms`, `rollout_path`, `cli_version` | 오늘 필터는 `updated_at_ms`. 스레드는 며칠 전에 시작해 오늘까지 이어질 수 있다. 사건 후보는 `thread_source = 'user'`만이고 `guardian_review`·`subagent`는 제외한다. 확인일에 `-shm` 파일이 있을 때는 `mode=ro`로 열렸고, 없을 때는 `&immutable=1`이 필요했다 |
| `~/.codex/thread_history_*.sqlite`의 `thread_items` | 항목. `thread_id`, `item_type`, `created_at_ms`, `item_json` | 확인일에 `-shm` 파일이 없어 `mode=ro`만으로 열리지 않았다. 아래 예시는 `&immutable=1`을 바로 쓴다. `thread_history_*.sqlite-shm`이 있으면 `mode=ro`를 먼저 시도한다 |
| `threads.rollout_path`(`~/.codex/sessions/YYYY/MM/DD/*.jsonl`) | 원본 롤아웃(JSONL 이벤트 로그). 날짜 폴더는 시작일 기준 | `thread_items`에 행이 없는 스레드의 폴백. 수백 MB일 수 있어 `grep -a`로 먼저 거른다 |
| `~/.codex/session_index.jsonl`, `~/.codex/history.jsonl`, `~/.codex/version.json` | 갱신이 멈춘 색인·업데이트 확인 캐시 | 쓰지 않는다 |

`item_type`으로 발화를 구분한다. 본문 경로는 `item_json` 안의 JSON 경로다.

| `item_type` | 본문 | 취급 |
|---|---|---|
| `userMessage` | `$.content[0].text` | 사용자 발화 |
| `agentMessage` | `$.text` | 결과 보고 근거 |
| `commandExecution` | `$.command` | 실행 근거. 재실행하지 않는다 |
| `fileChange` | `$.changes[].path` | 변경 근거 |
| `plan` | `$.text` | 계획 근거 |
| `reasoning`, `contextCompaction`, `webSearch`, `imageView`, `sleep` | — | 제외 |

예시(읽기 전용):

- 오늘 갱신된 사용자 스레드: `sqlite3 "file:$STATE_DB?mode=ro" "SELECT substr(id,1,13), datetime(updated_at_ms/1000,'unixepoch','+9 hours'), cwd, substr(replace(coalesce(title,''),char(10),' '),1,100) FROM threads WHERE thread_source='user' AND updated_at_ms>=$FROM_MS AND updated_at_ms<$TO_MS ORDER BY updated_at_ms;"`
- 오늘 항목 수(스레드·종류별, 먼저 본다): `sqlite3 "file:$HISTORY_DB?mode=ro&immutable=1" "SELECT substr(thread_id,1,13), item_type, COUNT(*) FROM thread_items WHERE created_at_ms>=$FROM_MS AND created_at_ms<$TO_MS GROUP BY thread_id, item_type;"`
- 오늘 발화와 보고(시각·스레드·종류·앞 100자, 앞 40건): `sqlite3 "file:$HISTORY_DB?mode=ro&immutable=1" "SELECT datetime(created_at_ms/1000,'unixepoch','+9 hours'), substr(thread_id,1,13), item_type, substr(replace(coalesce(json_extract(item_json,'$.content[0].text'), json_extract(item_json,'$.text')),char(10),' '),1,100) FROM thread_items WHERE created_at_ms>=$FROM_MS AND created_at_ms<$TO_MS AND item_type IN ('userMessage','agentMessage') ORDER BY created_at_ms LIMIT 40;"` 더 필요하면 `OFFSET`으로 이어 본다.
- 명령 실행·파일 변경은 필요할 때만 같은 형태로 본다: `item_type IN ('commandExecution','fileChange')`, 본문은 `json_extract(item_json,'$.command')`와 `json_extract(item_json,'$.changes[0].path')`, `LIMIT`를 둔다. 자율 실행 스레드 하나가 하루 수천 행을 남길 수 있다.
- 롤아웃 폴백(사용자 발화만): `grep -a '"type":"UserMessage"' "$ROLLOUT" | jq -r 'select(.type=="event_msg" and .payload.type=="item_completed")|[.timestamp, (.payload.item.content[0].text|gsub("\\s+";" ")|.[0:100])]|@tsv'`

한계: `thread_items`는 지연 반영되어 오늘 활동한 스레드에 행이 없을 수 있다. 그때 `rollout_path`를 읽되, 롤아웃의 줄별 `timestamp`는 `thread_source = 'user'`에서만 실제 시각이고 `guardian_review`·`subagent`는 시작 시각으로 고정되어 날짜 필터가 무의미하다. 롤아웃의 타입명은 PascalCase(`UserMessage`), SQLite는 camelCase(`userMessage`)다. `response_item`의 `role == "user"`는 시스템 주입이 섞이므로 사용자 발화로 쓰지 않는다. `id`는 앞 8자가 겹칠 수 있어 13자 이상으로 표시한다. `title`은 수만 자일 수 있어 `substr`로 자른다.

## 사용자 발화가 없는 날

전날 시작한 자율 실행이 오늘까지 이어지면 오늘 창에 `userMessage`는 0건이고 `agentMessage`·`commandExecution`·`fileChange`만 수천 건 남는다(확인일에 관찰). `userMessage`만 세면 “오늘 Codex 사용 없음”이라는 오답이 나온다.

- 사용자 발화가 0건이어도 `fileChange` 경로, `agentMessage` 앞부분, `commandExecution`으로 무엇을 했는지 한두 줄로 재구성한다.
- 첫 안내에서 “사용자 발화 없이 에이전트가 자율 실행”으로 구분하고, 그 결과를 확인했는지·개입했는지를 사용자에게 묻는다. 에이전트의 실행을 사용자의 직접 수행·이해로 쓰지 않는다.
- Claude Code에서도 `promptSource == "typed"`가 0건이고 서브에이전트·도구 결과만 있으면 같은 방식으로 다룬다.

## 두 도구의 기록을 합칠 때

- 보존 기간이 다르다(Claude Code 기본 30일, Codex는 사실상 무기한). 오래된 날짜는 한쪽만 조회될 수 있음을 밝힌다.
- 하루 형태가 다르다. Claude Code는 짧은 턴이 촘촘하고, Codex는 발화 없이 장시간 자율 실행이 가능하다. 채팅 수를 비교하지 않는다.
- 사건 최대 세 개를 고를 때 어느 도구의 기록인지 표시한다. 같은 작업을 두 도구에서 이어 했으면 한 사건으로 센다.
- 한쪽만 읽었거나 권한이 없으면 “Claude Code 기록만 확인했습니다”처럼 범위를 알린다.

## 변경 시 확인할 행동

도구를 업데이트했거나 조회가 비면 `claude --version`·`codex --version`으로 버전을, `ls ~/.codex/*.sqlite`로 파일명 접미사를, `PRAGMA table_info(threads)`·`PRAGMA table_info(thread_items)`로 컬럼을, 트랜스크립트 한 줄의 `keys`로 필드명을 다시 확인하고 확인일을 갱신한다. 하루 창 경계(전날 23:59, 당일 00:01)의 항목이 올바른 날짜에 들어가는지, 사용자 발화 0건인 날에 자율 실행 표기가 나오는지, `jq`·`sqlite3`가 없는 환경에서 예시를 생략하고 범위를 알리는지, 조회 출력에 원문 전체나 비밀정보가 섞이지 않는지 본다.
