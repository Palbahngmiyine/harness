# hwahap

Codex CLI 세션 하나에서 구현 요청을 `align → build → deliver → improve` 순서로 끌고 가는 오케스트레이션 스킬이다. 세션의 모델(오케스트레이터)은 `SKILL.md`의 고정 템플릿으로 `codex exec` 하위 프로세스를 띄우고, 결정적인 일은 전부 hook 4개와 jq 프로그램이 맡는다. Python은 0줄이고 shell과 jq만 쓴다.

이 문서는 사람과 LLM 모두를 위한 기준 문서다. 오케스트레이터가 실행 중에 읽는 것은 `SKILL.md`와 `SURFACES.md`뿐이며, 이 README는 설치, 구조, 실행 흐름, 설계 결정, 테스트 규칙을 기록한다. 코드와 이 문서가 어긋나면 코드를 기준으로 문서를 고친다. 이 스킬을 수정하는 에이전트는 §6 설계 결정과 §7 코드 규칙을 먼저 읽는다.

## 1. 한눈에 보기

| 단계 | 실행 주체 | 하는 일 | 강제하는 것 |
|---|---|---|---|
| align | 오케스트레이터와 사용자 | 12개 결정 표면을 검토해 `.hwahap/goal.json` 계약을 만든다. 저장소 사실은 fact worker가 조회한다 | `prompt.sh`가 사용자가 직접 친 답만 hash chain 원장에 기록. `check.jq`, cold review, `CONFIRM ALIGN` |
| build | worker(Luna)와 reviewer(Terra) | unit마다 detached worktree에서 patch를 만들고 독립 검토한다 | `pretool.sh`가 실행 전 검사, `posttool.sh`가 증거를 한 줄로 기록, `integrate.sh`가 통합 1회 |
| deliver | `gate.sh` (Stop hook) | 검사 전부 통과 시 `report.md`, `summary.json`, `hwahap/<goal_id>` branch, draft PR | 하나라도 실패하면 세션 종료를 막고 이유를 돌려준다 |
| improve | `improve-gate.sh` | 개선 신호와 시작 조건 6개를 판정해 기록한다 | benchmark 재실행 runner(U9b)는 미구현. 프로세스를 띄우지 않는다 |

## 2. 요구 사항과 설치

- Bash, jq(1.7.1에서 검증), git, 인증된 `gh`, Codex CLI 0.151 이상. Python은 필요 없다. 테스트를 로컬에서 돌리려면 ripgrep(`rg`)도 필요하다.
- 대상 저장소에서 `.hwahap`이 `.gitignore`에 있어야 한다. 없으면 오케스트레이터가 추가 여부를 묻는다.

```sh
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R skills/hwahap "${CODEX_HOME:-$HOME/.codex}/skills/"
```

그다음 `hooks/hooks.json`의 네 항목(UserPromptSubmit, PreToolUse, PostToolUse, Stop)을 `~/.codex/hooks.json`에 기존 hook을 지우지 않고 병합하고 Codex를 재시작한다. hooks.json은 `$HOME/.codex/skills/hwahap/hooks/*.sh`를 절대 경로로 부른다.

중첩 `codex exec`는 sandbox 안에서 `~/.codex/state_*.sqlite` 쓰기가 거부되어 실패한다. 첫 실행에서 escalation을 승인하고, 승인이 `~/.codex/rules/default.rules`에 자동 기록되지 않으면 아래 한 줄을 직접 넣고 재시작한다.

```
prefix_rule(pattern=["codex", "exec"], decision="allow")
```

improve 판정을 쓰려면 `~/.codex/hwahap/config.json`이 필요하다. 예시는 `config/config.json.example`이다.

## 3. 파일 구성

```
skills/hwahap/
  SKILL.md                  오케스트레이터 지시문. 100줄 이하. 템플릿 3개, 읽기 허용 목록, worker 결정 경계
  SURFACES.md               12개 결정 표면과 시나리오 질문 예
  hooks/hooks.json          ~/.codex/hooks.json에 병합할 등록 조각
  hooks/prompt.sh           UserPromptSubmit. 사람 turn 표시, 답변 원장 기록, skip 기록
  hooks/pretool.sh          PreToolUse. codex exec 템플릿·모델·align 게이트·cached·budget·의존 patch 검사
  hooks/posttool.sh         PostToolUse. worker/reviewer/fact 결과를 요약 한 줄로. usage 기록, 통합 트리거
  hooks/gate.sh             Stop. 검사 전부, report.md, summary.json, deliver, improve 판정, run 보관
  hooks/lib/capture.sh      worker patch·scope·test·usage·재시도 기록
  hooks/lib/integrate.sh    patch를 위상 순서로 적용하고 full_suite 1회 실행. mkdir 잠금으로 이중 실행 방지
  hooks/lib/deliver.sh      생성 branch commit, push, draft PR
  hooks/lib/usage.sh        validate(모델·effort 대조), record(usage 기록), metrics(역할별 합산)
  hooks/lib/improve-gate.sh improve 신호와 시작 조건 판정. 프로세스를 띄우지 않는다
  jq/check.jq               goal.json 규칙 검사
  jq/render.jq              goal.json → align.md. 같은 입력이면 바이트 동일
  jq/brief.jq               goal.json → worker, reviewer, cold, fact brief
  jq/usage.jq               events.jsonl → usage.json
  data/settings.json        역할별 model, effort, tool_output_token_limit의 단일 출처
  data/prices.json          모델 단가표. 갱신일 포함
  data/brief.head.md        worker brief 고정 머리말
  data/secrets.regex        인도 전 비밀 패턴
  config/config.json.example  ~/.codex/hwahap/config.json 예시
  tests/                    §8
```

## 4. 실행 흐름

### 4.0 사전 확인

`jq --version`, `gh auth status`, `git check-ignore -q .hwahap` 세 명령이 전부 성공해야 `.hwahap`을 만든다. 문서-only 요청, 질문, 아이디어 탐색에는 이 스킬을 쓰지 않는다.

### 4.1 align

1. 오케스트레이터가 `.hwahap/goal.json`을 만든다. `schema: hwahap/v2`, `base_branch`(현재 branch, detached면 기본 branch), `revision: 1`, goal 문장. 기술 스택을 먼저 묻는다.
2. `SURFACES.md`의 12개 표면을 순서대로 검토한다. 해당하는 표면마다 `kind: decision` choice와 "이 상황에서 무엇이 일어나야 하는가"를 묻는 `kind: scenario` choice를 하나 이상 낸다. 용어가 코드나 앞선 발화와 다르면 `kind: term` choice로 확정한다.
3. 저장소나 환경에서 알 수 있는 사실은 사용자에게 묻지 않는다. fact 템플릿으로 조회해 `.hwahap/facts/F<n>.md`에 남기고 choice의 `evidence`에서 `F<n>`으로 인용한다. fact를 기다리지 않고 그것에 의존하지 않는 질문을 먼저 낸다.
4. 사용자 답변 문법은 여섯 가지뿐이다. `C<n>=ALT<m>`, `C<n>=OTHER: <값>`, `C<n>=UNKNOWN`, `S<n>=NA`, `CP<k>=OK`, `CONFIRM ALIGN`. "ok", "추천대로" 같은 문장은 기록되지 않으며 같은 질문을 다시 낸다.
5. `prompt.sh`가 답변을 `.hwahap/answers.jsonl`과 `~/.codex/hwahap/<repo-id>/answers.jsonl` 양쪽에 같은 줄로 append 한다. 각 줄은 답이 가리키는 항목(choice의 `{id, question, alternatives}`, NA 표면의 `{id, reason}`, checkpoint의 `same_as_recommendation`)의 sha256에 결속되고 이전 줄 해시와 체인으로 이어진다. 오케스트레이터는 원장을 쓰지 않는다.
6. 해당 없음은 오케스트레이터가 이유를 적고 사용자가 `S<n>=NA`를 쳐야 확정된다. round 번호가 4의 배수일 때는 `CP<k>=OK` checkpoint가 있어야 한다. applicable choice가 40개를 넘거나 round가 6을 넘으면 goal 분할을 제안한다.
7. `UNKNOWN`은 open item이 된다. 사실로 풀리면 fact, 반응이 필요하면 `probe: true` unit이다. probe unit은 worker 템플릿으로 실행되지만 통합과 인도에서 제외된다. open item이 남아 있으면 확정할 수 없다.
8. frontier가 비면 spec, acceptance, atomic unit, DAG를 쓰고 `jq -e -f jq/check.jq .hwahap/goal.json`을 통과시킨다. cold review(reviewer 템플릿, `-C .`, 출력 `out/review/cold.md`)를 돌려 `required_user_choices`, `underspecified`, `unmapped_spec_ids` 세 목록이 빌 때까지 반복한다. `posttool.sh`가 통과한 cold review를 goal 해시와 함께 `review.cold`에 기록한다.
9. `jq -r -f jq/render.jq .hwahap/goal.json > .hwahap/align.md`로 결정적으로 렌더링하고 사용자가 그 파일을 읽은 뒤 `CONFIRM ALIGN`을 친다. `prompt.sh`가 goal 해시와 `align.md` 해시를 함께 stamp 한다. 이후 goal.json이 바뀌면 gate가 거부한다.

### 4.2 build

1. 의존성이 해결된 unit을 `budget.max_parallel`까지 한 batch로 묶는다. unit마다 `git worktree add --detach .hwahap/wt/<unit> HEAD`와 `brief.jq`로 `out/<unit>.brief.md`를 만든다. brief는 손으로 쓰거나 출력하지 않는다.
2. worker 템플릿을 unit당 한 줄의 직접 명령으로 실행한다. `for … & done; wait` 같은 shell 래퍼는 allow rule에 매치되지 않으므로 batch는 같은 턴의 병렬 도구 호출로 낸다. brief는 stdin, 이벤트는 `--json`으로 `out/<unit>.events.jsonl`, 마지막 메시지는 `-o out/<unit>.last.md`.
3. `pretool.sh`가 실행 전에 순서대로 검사하고 하나라도 실패하면 `permissionDecision: deny`와 올바른 템플릿을 돌려준다. 필수 플래그, `-m`과 `model_reasoning_effort`가 `settings.json`(unit에 override가 있으면 그 값)과 일치, align 게이트(원장 대조, goal·render 해시, revision, open item), brief가 `brief.jq` 현재 출력과 바이트 동일, cached 조건, `needs_decision` 잔존, budget 100%, 시도 2회 미만, 선행 unit patch 적용(전이 의존 포함, 위상 순서, `--check` 뒤 적용, private index).
4. `posttool.sh`가 실행 뒤 `capture.sh`로 patch(`HEAD` 또는 private index 기준 diff), 변경 경로가 unit `paths` 안인지, unit `test` 실행 결과, usage를 기록하고 한 줄을 돌려준다. 형식은 `U1 pass|fail|needs_decision tokens=<n> cost=<usd> cache=<ratio> budget=<pct>%`이며 필요 시 ` network=1`, ` usage_error=1`이 붙는다. 오케스트레이터는 이 줄만 읽는다.
5. `fail`이면 같은 템플릿으로 한 번 더 실행한다. `brief.jq`가 실패 출력을 brief 끝에 붙인다. 두 번째도 실패면 사용자에게 `retry`, `skip`, `abort`를 묻는다. `skip U<n>`은 `prompt.sh`가 `out/U<n>.skipped`로 기록하고, skip한 unit에 의존하는 unit은 실행하지 않는다.
6. 통과한 unit마다 reviewer 템플릿(`-s read-only`)을 실행한다. 출력 첫 줄은 `verdict: pass` 또는 `verdict: fail`이고 finding은 `- [paths|intent|test] 설명`이다. fail이면 finding을 brief에 붙여 2단계로 돌아간다. 라운드 상한은 2회다. 형식이 틀리면 `verdict_invalid=1`이 붙고 fail로 취급한다.
7. 모든 `probe: false` unit이 pass이고 verdict가 pass이면 마지막 reviewer의 `posttool.sh`가 `integrate.sh`를 부른다. patch를 위상 순서로 `.hwahap/wt/integration`에 `--check` 뒤 적용하고 `full_suite`를 한 번 실행해 `out/integration.test.txt`에 기록한다. 요약 줄에 ` integration=pass|fail`이 붙는다.
8. 오케스트레이터의 마지막 명령은 통합 검토다. reviewer 템플릿을 `--arg unit integration`으로 실행하고 `final_review`가 `sol`이면 `-m gpt-5.6-sol`로 바꾼다.
9. worker가 자기 unit 안에서 되돌릴 수 있고 관찰 가능한 동작, 식별자, 경로, 포맷, 스키마, 저장 필드, 의존성, 동시성, 보안, 성능, 호환성에 영향이 없는 것만 스스로 정한다. 그 밖의 결정을 만나면 코드를 바꾸지 않고 마지막 메시지 첫 줄에 `NEEDS_DECISION: <질문>`을 쓴다. 오케스트레이터는 그것을 새 choice로 내고 revision을 올려 cold review, render, `CONFIRM ALIGN`을 다시 받는다. brief가 바뀌지 않은 unit은 `cached`로 건너뛴다.
10. budget은 worker, reviewer, fact 토큰의 합이다. 요약 줄의 `budget=` 값이 50% 알림이고, 80%에 `out/budget.warn`이 생기며, 100%에 `pretool.sh`가 새 worker를 거부한다.

### 4.3 Stop gate와 deliver

세션이 끝나면 `gate.sh`가 순서대로 검사한다. 실패하면 `{"decision":"block","reason":"…"}`으로 종료를 막고 이유를 오케스트레이터에게 돌려준다. worker 산출물이 없는 align 세션은 앞 10개만 검사하고 실패해도 종료를 막지 않는다. 재진입(`stop_hook_active: true`)은 차단하지 않는다.

1. `review.cold.goal_sha256`이 현재 goal 해시(`review`와 `confirm`을 뺀 `jq -S -c` 문서의 sha256)와 같다.
2. `confirm.goal_sha256`이 같고 `confirm.revision`이 `revision`과 같다.
3. 원장이 workspace 안팎에 모두 있고, JSON으로 파싱되며, 안쪽 모든 줄이 바깥에 그대로 있다.
4. 모든 choice 답, `S<n>=NA`, `CP<k>=OK`, `CONFIRM`이 원장 항목에 결속돼 있다.
5. `render.jq`를 다시 돌린 출력의 sha256이 `confirm.render_sha256`과 같다.
6. 원장 hash chain이 연속이고 각 줄의 해시가 맞다.
7. `check.jq` 통과. 8. open item 없음. 9. `facts[]` 파일이 존재하고 sha256이 기록값과 같다.
10. (build일 때) `needs_decision` 없음. 각 `probe: false` unit에 patch, `exit 0`으로 끝나는 test.txt, `verdict: pass` review가 있고 patch 경로가 `paths` 안이다. skip한 unit은 `.skipped`가 있다.
11. 통합 테스트가 `exit 0`, 통합 검토가 `verdict: pass`, 통합 diff 경로가 모든 unit `paths` 합집합 안이다.
12. `human.turn` 시각이 `confirm.ts` 이상이다. 사람이 확정한 뒤 시작된 build만 인도한다.
13. 통합 diff에 `secrets.regex` 패턴이 없다.

통과하면 `report.md`(결론, 근거, 확인 과정, 한계, 비용 순서)와 `summary.json`을 쓰고 `deliver.sh`를 부른다. deliver는 `hwahap/<goal_id>` branch를 만들어 unit `paths`만 `git add`, `Hwahap-Goal`과 `Hwahap-Revision` trailer로 commit, push, `gh pr create --draft --base <base_branch> --body-file report.md`를 한다. `main`, `master`, `develop`, `release/*`, `base_branch` 자체에는 push 하지 않으며 이 목록은 스크립트 상수다. 같은 branch나 열린 PR이 있으면 `skipped:exists`, `HWAHAP_UNATTENDED=1`이면 `skipped:unattended`, 그 밖의 실패는 `failed:<단계>`로 `out/deliver.txt`와 `summary.json`에 남는다. 하네스는 PR을 ready로 바꾸거나 merge 하거나 auto-merge를 켜지 않는다. deliver 실패는 종료를 막지 않는다.

그 뒤 `improve-gate.sh`를 부르고 `goal.json`, `summary.json`, `report.md`를 `~/.codex/hwahap/<repo-id>/runs/<goal_id>/`에 복사한다. 오케스트레이터 토큰은 세션 rollout 파일의 마지막 `token_count`에서 읽고, 못 찾으면 보고서에 측정 불가로 적는다.

### 4.4 improve

`improve-gate.sh`가 조건을 순서대로 판정하고 첫 실패 조건을 `summary.json`의 `improve.reason`에 적는다.

1. `~/.codex/hwahap/config.json`에 `improve.auto`가 `true`이고 `improve.budget_tokens`가 있다.
2. `harness_repo`가 있고 git 저장소다.
3. 신호가 있다. 판정 순서는 `cost_above_median`(이번 run의 `cost_per_passed_unit`이 같은 repo의 다른 run 중앙값보다 큼), `retry_seen`(`first_try_pass < units_passed`), `cache_miss`(`cache_hit_ratio < 0.5`)이며 첫 일치가 신호다.
4. `improve.state.json`의 `last_auto`가 7일 이전이다. 파일이 없으면 통과다. 시각은 `Z`와 `+HHMM` 오프셋 둘 다 읽는다.
5. 같은 repo의 benchmark(현재 goal을 뺀 `runs/*/summary.json`)가 5개 이상이다.
6. deliver가 `done`이다. PR 없이 improve를 돌리지 않는다.

여섯 조건이 모두 참이어도 프로세스를 띄우지 않고 `improve.started=false`, `reason="runner pending (U9b)"`를 기록한다. 미구현 항목은 `hooks/lib/improve.sh`, benchmark 재실행 runner, ruler(가장 작은 benchmark 3회 재실행으로 noise band `max(2σ, 평균의 10%)`), canary(worker effort를 medium으로 낮춰 band 밖 차이 확인), proposer(Sol medium, 허용 범위는 `settings.json`과 `brief.head.md`, unified diff 하나), keep/revert, `hwahap-improve/<date>` draft PR, 3회 연속 무성과 시 `improve.auto=false`다. `summary.json`의 `base_sha`와 `repo_path`는 이 재실행을 위해 지금부터 기록한다.

lesson은 사용자가 gate 실패, 자신의 수정, 되돌린 patch, reviewer가 잡은 worker의 추측 중 하나를 말했을 때만 오케스트레이터가 한두 문장으로 제안하고, 동의하면 `~/.codex/hwahap/lessons.candidates.md`에 한 줄로 append 한다. 규칙으로 옮기는 것은 사용자가 한다.

## 5. 데이터와 파일

### 대상 저장소 `.hwahap/` (git 추적 안 함)

```
goal.json                 계약. 규칙은 jq/check.jq
align.md                  render.jq 출력. CONFIRM ALIGN이 이 파일의 해시에 결속
answers.jsonl             prompt.sh가 쓰는 답변 원장 (hash chain)
diary.md                  오케스트레이터 일지. Deviations와 Open questions 절이 report.md 한계에 들어감
human.turn                사람 turn 시각
facts/F<n>.md .events.jsonl .usage.json
wt/<unit>/  wt/integration/
out/<unit>.brief.md .brief.sha256 .events.jsonl .last.md .patch .test.txt .usage.<attempt>.json .usage.json
out/<unit>.attempt .skipped .needs_decision .cached .base-index .capture.err
out/review/<unit>.md .brief.md .events.jsonl .usage.<n>.json .attempt   (unit, cold, integration)
out/integration.test.txt  out/integration.lock  out/budget.warn  out/deliver.txt
report.md  summary.json
```

### workspace 밖 `~/.codex/hwahap/`

```
config.json                       harness_repo, improve.auto, improve.budget_tokens
<repo-id>/answers.jsonl           원장 사본. repo-id는 git toplevel 경로 sha256의 앞 16자
<repo-id>/runs/<goal_id>/         goal.json, summary.json, report.md. improve의 benchmark
<repo-id>/improve.state.json      last_auto (U9b가 쓴다)
lessons.candidates.md             lesson 후보
```

### summary.json

`goal_id`, `revision`, `base_branch`, `base_sha`, `repo_path`, `units_total`, `units_passed`, `units_cached`, `first_try_pass`, `tokens.{workers,reviewers,facts,orchestrator}`, `units[].{id,cache_hit_ratio,reasoning_ratio}`, `cache_hit_ratio`, `cost_usd`, `cost_per_passed_unit`, `seconds`, `pr_url`, `deliver`, `improve.{signal,started,reason,benchmark_count}`, `config.{worker_model,worker_effort,reviewer_model,reviewer_effort,max_parallel}`.

### usage.json

`usage.jq`가 `events.jsonl`의 `turn.completed.usage`를 합산한다. `unit`, `attempt`, `model`, `effort`, `input_tokens`, `cached_input_tokens`, `output_tokens`, `reasoning_output_tokens`, `cache_hit_ratio`, `reasoning_ratio`, `cost_usd`(`prices.json`의 input, cached_input, output 단가), `started`, `ended`, `seconds`. 역할은 경로로 구분한다. worker `out/*.usage.<n>.json`, reviewer `out/review/*.usage.<n>.json`, fact `facts/*.usage.json`.

### 환경변수

| 이름 | 의미 |
|---|---|
| `HWAHAP_NOW` | 시각 주입. 테스트는 항상 이것을 쓴다 |
| `HWAHAP_UNATTENDED=1` | gate는 판정만 하고 인도하지 않는다. prompt.sh도 기록하지 않는다 |
| `HWAHAP_DISABLE_HOOKS=1` | hook 네 개가 즉시 exit 0 |
| `HWAHAP_NO_CACHE=1` | cached 판정을 끈다 |
| `HWAHAP_SECONDS` | usage의 seconds 주입 |
| `CODEX_HOME` | `~/.codex` 대체 경로 |

## 6. 설계 결정

번호는 2026-09-02 기획(PR #8)의 결정 번호다. 2026-09-03 승인 메시지로 바뀐 것은 끝에 적었다.

역할과 프로세스
- worker, reviewer, fact worker는 오케스트레이터가 템플릿을 복사해 자기 shell로 띄우는 `codex exec` 하위 프로세스다. 세션 subagent는 쓰지 않으므로 thread limit이 없다 (D4).
- 기본 모델은 worker Luna high, reviewer Terra high, fact Luna medium, proposer Sol medium이며 `data/settings.json`이 단일 출처다. unit의 `model`, `effort`로 worker만 override 할 수 있다 (D7). 오케스트레이터 모델은 사용자 설정이며 권장은 align 중 high 이상, build 중 medium이다.
- worker는 `--ignore-user-config`, `web_search=disabled`, `model_verbosity=low`, `model_reasoning_summary=none`, `tool_output_token_limit=4000`으로 뜬다 (D38). 마지막 메시지는 변경 요약 한 문단이거나 `NEEDS_DECISION` 한 줄이다.
- 템플릿은 SKILL.md의 세 개뿐이고 오케스트레이터는 unit id와 질문만 바꾼다. `pretool.sh`가 필수 플래그와 모델 값을 검사하고 거부 이유에 템플릿을 넣는다 (D49).
- 세 역할 모두 `--json`으로 이벤트를 남기고 budget과 비용은 세 역할의 합이다. 오케스트레이터 토큰은 따로 잰다 (D17).

git과 파일
- build 중 하네스는 `git commit`, `git add`, `git stash`를 실행하지 않는다. 허용 명령은 `worktree add/remove/list`, `diff`, `apply`, `hash-object`, `rev-parse`, `status`, `ls-files`뿐이며 선행 patch는 `GIT_INDEX_FILE` private index로 적용한다. commit, push, branch 생성은 `deliver.sh`가 생성 branch에만 한다 (D5).
- unit마다 detached worktree, 산출물은 patch 파일이다. 상태 기계와 ledger는 없고 파일의 존재와 해시가 상태다.
- 오케스트레이터가 읽을 수 있는 것은 posttool 요약 줄, `out/review/*.md` 첫 줄, `out/*.needs_decision`, `facts/F<n>.md`, `report.md`뿐이다. `events.jsonl`, patch, `last.md`는 읽지 않는다 (D44).
- 통과한 unit은 brief 해시가 같으면 다시 실행하지 않는다 (D37). worker brief에는 그 unit의 `paths`, `test`, spec, acceptance, term만, reviewer brief에는 patch 전문과 같은 항목만 들어간다 (D39, D40).

align
- 해당 없음은 사용자만 `S<n>=NA`로 확정한다 (D28). `CONFIRM ALIGN`은 결정적 render의 해시에 결속된다 (D29). 사실은 묻지 않고 fact worker가 조회한다 (D30). round마다 답에서 파생된 choice를 추가하고 마지막 round는 새 choice가 0개여야 한다 (D31). `UNKNOWN`은 fact 또는 probe unit이다 (D32). 40 choice 또는 6 round를 넘으면 분할 제안 (D33). term, scenario, 코드 대조 세 규칙 (D34). 답변 문법 여섯 가지 (D48). revision이 오르면 새 `CONFIRM ALIGN`이 필요하고 이전 답은 유효하다 (D47).

build
- `CONFIRM ALIGN` 뒤 build는 자율이다. 사람에게 묻는 경우는 2회 실패, budget 100%, 통합 충돌, `NEEDS_DECISION`뿐이며 `CONFIRM BUILD`는 없다 (D21). worker 시도 2회, reviewer 2라운드 (D18). budget 알림 50, 80, 100% (D43). batch는 같은 템플릿으로 동시에 시작해 brief 머리말 cache를 공유하고, batch 사이를 5분 이상 비우지 않는다 (D42). unit 테스트는 그 unit의 `test`만, `full_suite`는 통합 뒤 한 번 (D41). probe unit은 통합과 인도에서 제외하고 토큰은 align 비용이다 (D46). `summary.json`은 unit마다 `cache_hit_ratio`와 `reasoning_ratio`를 기록한다 (D45).

deliver와 improve
- Stop gate 통과 시 `hwahap/<goal_id>` branch로 draft PR을 연다 (D22). head branch 접두사는 `hwahap/`, `hwahap-improve/`이고 금지 목록은 설정으로 넓힐 수 없다 (D23). ready, merge, auto-merge 금지. 중복 branch나 PR이 있으면 사용자에게 묻는다 (D24). `HWAHAP_UNATTENDED=1`은 판정만 (D25).
- 자동 improve는 신호, 7일, benchmark 5개, `improve.auto`, `budget_tokens`가 모두 있을 때만 시작하고 budget은 hard cap이다 (D26). 3회 연속 무성과이면 `improve.auto=false` (D27). improve 단계는 benchmark 없이 설정을 바꾸지 않고 proposer는 제안만, keep/revert는 코드가 정한다.

코드 형태
- 파일당 80줄 이하, jq 프로그램 4개 (D12). 방어 코드 없음, 같은 조건 두 번 검사 안 함, 잘못된 입력은 첫 검사에서 이유를 출력하고 exit 1 (D13). `if`와 `[ ]`에 `&&`, `||` 복합 조건 없음. 조건 하나가 결정 하나다 (D14). 시간 의존 테스트와 `sleep` 없음, 시각은 `HWAHAP_NOW` (D15). 보고서는 markdown 하나 (D16). 대상 플랫폼은 Codex CLI 0.151 이상이며 Claude Code 어댑터는 범위 밖이다 (D20).

2026-09-03 승인 메시지로 바뀐 것
- reviewer와 fact 템플릿도 `--json`을 쓰고 stdout을 `events.jsonl`로 리다이렉트한다. D17의 합산이 실제로 가능해졌다.
- `data/settings.json`이 모델·effort의 단일 출처가 되고 `pretool.sh`가 값을 대조한다. `tests/templates.sh`가 SKILL.md 템플릿과 대조한다.
- coverage 기준은 "kcov executable-line 100% + mutation 100%"다. kcov는 bash를 PS4 또는 DEBUG trap으로 실행된 줄만 재므로 branch coverage를 낼 수 없다. mutation은 `if` 조건과 `<검사> || deny|fail|exit|{` 가드를 모두 뒤집는다.
- U9는 U9a(신호 판정)와 U9b(runner)로 나뉘고 U9b는 보류다. `summary.json`에 `base_sha`, `repo_path`가 추가됐다.
- 80줄을 넘는 hook은 `hooks/lib/`로 나눌 수 있다. 그래서 helper가 `usage.sh`, `improve-gate.sh`를 포함해 5개다.

## 7. 코드 규칙

이 스킬을 고치는 사람과 에이전트가 지킬 것.

- 스크립트마다 2행 주석에 책임 한 문장을 적는다. 주석과 동작이 다르면 둘 다 고친다.
- 모든 exit 1 경로에 stderr 메시지가 있고 `tests/lint-messages.sh`가 그 문자열이 tests/ 어딘가에 등장하는지 검사한다. 메시지를 추가하면 fixture도 추가한다.
- `data/brief.head.md`와 SKILL.md의 템플릿 3개는 손으로 바꾸지 않는다. 바꾸면 cached 판정과 `pretool.sh` 검사가 어긋나므로 측정과 함께 improve 단계에서만 바꾼다.
- `deliver.sh`와 improve의 git, gh 호출은 전부 shim으로 테스트한다. 테스트가 실제 remote에 push 하는 일은 없어야 한다.
- 버그가 보고되면 `tests/fixtures/regress/<id>/`를 먼저 만들어 실패를 확인한 뒤 고친다. fixture 없는 수정은 받지 않는다.
- 변이 대상에서 빼야 하는 조건은 같은 줄 끝에 `# MUTATION-IGNORE <이유>`를 적는다. 현재 허용된 사유는 `sha256sum`과 `shasum` 대체뿐이다.
- 새 파일, 필드, 명령을 추가하려면 이 README §6에 결정을 먼저 적는다.

## 8. 테스트와 CI

로컬 실행. bash, jq, git, `rg`만 있으면 결정적 스위트 전체가 돈다.

```sh
skills/hwahap/tests/all.sh        # 결정적 스위트, fuzz, lint 전부
skills/hwahap/tests/mutate.sh     # mutation 100% 요구
bats skills/hwahap/tests/all.bats # bats 설치 시. 각 스위트를 독립 항목으로
skills/hwahap/tests/coverage.sh   # kcov 설치 시 (Linux). executable-line 100% 요구
```

| 파일 | 검사하는 것 |
|---|---|
| `check.sh`, `fuzz/goal.sh` | `check.jq`의 goal.json 규칙. 유효 fixture와 키 삭제, 타입 변경, 순환, 경로 이탈 등 변형 거부 |
| `prompt.sh`, `fuzz/answers.sh` | 답변 문법, 원장 결속, hash chain, 위조 거부, `CONFIRM ALIGN`, skip |
| `brief-usage.sh` | `brief.jq` 결정성, `usage.jq` 합산과 단가 |
| `capture-posttool.sh` | patch 추출, scope 이탈, test 실행, NEEDS_DECISION, budget 50/80, usage_error |
| `pretool-posttool.sh`, `fuzz/command.sh` | 템플릿 플래그·모델 검사, align 게이트, cached, budget 100%, 시도 상한, 의존 patch, reviewer 경로 |
| `integrate.sh`, `fuzz/patch.sh` | 위상 순서 적용, 충돌, 한 번만 실행, 잠금 |
| `gate.sh` | Stop 검사 각각의 실패 fixture와 전체 통과, report·summary 형식. `improve-gate.sh`를 안에서 부른다 |
| `improve-gate.sh` | 신호 3종, 신호 없음, benchmark 4/5 경계, 7일 경계, auto=false, budget_tokens 없음, harness_repo 없음·비git, deliver 미완료 |
| `deliver.sh` | gh와 git shim, 로컬 bare origin. 성공, 중복 branch/PR, push 거부, 인증 실패, unattended, 재실행 시 done 유지 |
| `e2e.sh` | API 없이 align, worker, review, 통합, gate, deliver 전체. `fixtures/bin/codex`가 `-o`에 마지막 메시지를 쓰고 stdout에 JSONL을 낸다 |
| `boundary.sh` | `max_parallel` 1과 4의 산출물이 동일 |
| `lint-conditions.sh` | D14 복합 조건, helper 개수 |
| `lint-messages.sh` | deny/fail 메시지마다 fixture 존재 |
| `templates.sh` | SKILL.md 템플릿 값과 `settings.json` 일치 |
| `resources.sh` | 임시 파일·프로세스·worktree 누수 |
| `coverage-contract.sh` | `coverage.sh`가 kcov의 백분율 문자열을 숫자로 비교 |
| `mutate.sh` | `if`와 가드 조건 반전, `check.jq` 규칙 삭제. 살아남는 변형이 있으면 실패 |
| `CHECKLIST.md` | 사람이 실행하는 실제 모델 smoke 항목 |

CI는 `.github/workflows/hwahap-v2.yml`이다. `test` job이 ubuntu와 macOS matrix로 결정적 스위트, bats, shellcheck, jq 문법, lint 3종, 자원 누수를 돌리고 Linux에서만 kcov와 mutation을 돌린다. `verify` job은 matrix 전체가 성공했을 때만 성공하며 main branch 보호 규칙의 필수 체크 이름이다. matrix를 바꿔도 `verify` 이름은 유지한다.

## 9. 검증된 플랫폼 사실

2026-09-02, macOS, Codex CLI 0.152.1에서 실제로 확인한 값이다. 버전이 오르면 다시 확인한다.

- hook payload 공통 필드는 `session_id`, `transcript_path`, `cwd`, `hook_event_name`, `model`, `permission_mode`, `turn_id`. UserPromptSubmit은 `prompt`, PreToolUse는 `tool_name`, `tool_input.command`, `tool_use_id`, PostToolUse는 거기에 `tool_response`, Stop은 `last_assistant_message`, `stop_hook_active`.
- PreToolUse 거부는 stdout JSON `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"…"}}`이며 명령 실행 전에 막힌다. Stop 차단은 `{"decision":"block","reason":"…"}`이고 continuation을 한 번 만든다. 재진입은 `stop_hook_active: true`로 온다.
- Stop hook이 `nohup … &`로 남긴 프로세스는 hook 종료 뒤에도 살아 있다. `async` 설정은 필요 없다.
- 세션 rollout은 `~/.codex/sessions/YYYY/MM/DD/rollout-*-<session_id>.jsonl`이고 마지막 `token_count.info.total_token_usage`에 `input_tokens`, `cached_input_tokens`, `cache_write_input_tokens`, `output_tokens`, `reasoning_output_tokens`, `total_tokens`가 있다.
- `--ignore-user-config`로 뜬 worker는 MCP 없음, web_search 가능(그래서 `web_search=disabled`가 필요), 전역 `AGENTS.md` 로드됨(그래서 brief 머리말의 commit 금지가 필요).
- allow rule은 직접 `codex exec …` 명령에만 매치된다. `bash -lc 'for …; codex exec … & done; wait'`는 매치 0개다. 승인 뒤에도 `~/.codex/rules/default.rules`에 규칙이 자동 기록되지 않았으므로 §2의 수동 규칙이 필요하다.
- `codex exec`는 프롬프트 인자 없이 stdin의 brief를 읽는다.
- `gh auth status`와 `git ls-remote origin`이 되는 환경에서만 deliver가 성공한다. 실패하면 `report.md`와 `out/deliver.txt`에 이유가 남는다.

## 10. 알려진 한계

- hook은 `codex exec`로 시작하는 명령만 검사한다. 오케스트레이터가 다른 shell 명령으로 산출물을 직접 쓰는 것은 막지 않으며, 그 경계는 reviewer와 사람의 draft PR 검토가 잡는다. 이것은 설계 선택이다.
- 같은 choice에 답을 여러 번 바꾼 경우 원장은 "그 답이 입력된 적 있는가"만 증명한다. 최신 답인지는 사용자가 `align.md`를 읽고 `CONFIRM ALIGN`으로 확정한다.
- `.hwahap/`과 `~/.codex/hwahap/`의 파일 권한은 umask 기본값이다.
- worker 템플릿의 `-o` 경로는 검사하지 않는다. 템플릿을 그대로 복사하면 문제없다.
- 오케스트레이터 토큰은 rollout 파일을 찾지 못하면 측정 불가로 남는다.
- U9b가 없으므로 improve는 판정과 기록까지만 한다.

## 11. 이력

- 2026-09-02: PR #8에서 기획을 개정 1~3까지 고정. 근거 자료는 Uber Efficient Software Factory, SQLite testing, KiroCrew auto_improvement, AI-DLC stage protocol과 hooks.
- 2026-09-03: PR #9에서 U1~U8, U10, U9a 구현과 리뷰 반영. 기획 문서는 이 README로 대체하고 삭제했다. 상세 결정 근거는 PR #8과 #9의 본문과 코멘트에 남아 있다.
