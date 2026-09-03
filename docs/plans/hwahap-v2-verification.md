# hwahap v2 U1 플랫폼 확인

확인일: 2026-09-02 (Asia/Seoul)
대상: macOS, Codex CLI 0.152.1, PR #8 head `d22303c`

## 결론

§11의 아홉 항목을 모두 관찰했다. hook 네 이벤트, PreToolUse deny, Stop
continuation, JSONL usage, stdin brief, background 실행은 지원된다. 실행 템플릿은
복합 shell이 아니라 unit당 한 개의 `codex exec` 명령을 사용해야 한다.

## 확인 결과

1. **sandbox와 승인**
   - sandbox 안의 `codex exec`는 `~/.codex/state_5.sqlite` 쓰기가 거부되어 실패했다.
   - 같은 명령을 승인 후 sandbox 밖에서 실행하면 `READY`와 exit 0을 반환했다.
   - 승인 뒤에도 `~/.codex/rules/default.rules`에는 `codex exec` 규칙이 생기지 않았다.
   - fallback: 사용자가 설치 시 아래 규칙을 직접 추가하고 Codex를 재시작한다.
     `prefix_rule(pattern=["codex", "exec"], decision="allow")`

2. **`--ignore-user-config` 범위**
   - 격리 worker의 관찰값은 `MCP=NONE`, `WEB_SEARCH=available`,
     `GLOBAL_AGENTS=loaded`였다.
   - 따라서 worker 템플릿의 `web_search=disabled`와 brief의 commit 금지는 필요하다.

3. **hook payload**
   - 공통: `session_id`, `transcript_path`, `cwd`, `hook_event_name`, `model`,
     `permission_mode`, `turn_id`.
   - UserPromptSubmit: `prompt`.
   - PreToolUse: `tool_name`, `tool_input.command`, `tool_use_id`.
   - PostToolUse: `tool_name`, `tool_input.command`, `tool_response`, `tool_use_id`.
   - Stop: `last_assistant_message`, `stop_hook_active`.

4. **차단 규약**
   - PreToolUse의 `hookSpecificOutput.permissionDecision=deny`는 `pwd` 실행 전에
     `Command blocked by PreToolUse hook`으로 차단했다.
   - Stop의 `{"decision":"block","reason":"..."}`은 continuation을 한 번 만들었다.
     재진입은 payload의 `stop_hook_active: true`에서 차단하지 않아야 한다.

5. **rollout과 token usage**
   - 현재 세션은 `~/.codex/sessions/YYYY/MM/DD/rollout-*-<session_id>.jsonl`에서 찾았다.
   - 마지막 `token_count.info.total_token_usage`에 `input_tokens`,
     `cached_input_tokens`, `cache_write_input_tokens`, `output_tokens`,
     `reasoning_output_tokens`, `total_tokens`가 있었다.

6. **Stop background 실행**
   - Stop hook이 `nohup sleep 30 >/dev/null 2>&1 &`를 시작한 실행은 3.33초에 끝났다.
   - 부모 종료 직후 background PID가 살아 있었으므로 `async` fallback은 필요 없다.

7. **GitHub 인도 경로**
   - `gh auth status`는 `Palbahngmiyine` 계정으로 성공했다.
   - `git ls-remote origin`은 `main`과 PR #8 head를 반환했다.
   - 관찰 시점의 인증 성공이며 실제 deliver 성공 증명은 아니다.

8. **Rules 명령 매칭**
   - `codex execpolicy check`에서 직접 `codex exec ...`는 allow rule과 매치됐다.
   - `bash -lc 'for ...; codex exec ... > ... & done; wait'`는 매치가 0개였다.
   - fallback: unit당 한 줄의 직접 명령을 같은 턴에 병렬 실행한다.

9. **stdin brief**
   - `printf ... | codex exec ... -`가 `STDIN only.`와 exit 0을 반환했다.
   - worker와 reviewer brief는 command argument가 아니라 stdin으로 전달한다.

## 사전 조건과 한계

- `jq 1.7.1`, `gh auth status`, `git check-ignore -q .hwahap`은 통과했다.
- 로컬에는 `bats`, `shellcheck`, `kcov`가 없다. U8의 CI와 설치된 환경에서 검증한다.
- payload 캡처는 검증용 `--dangerously-bypass-hook-trust`로 저장소의 no-op hook만
  실행했다. 이 플래그는 실제 hwahap 템플릿에 포함하지 않는다.

## 공식 근거

- [OpenAI Docs: Hooks](https://learn.chatgpt.com/docs/hooks): 이벤트 payload,
  PreToolUse deny, Stop continuation, background hook 계약.
- [OpenAI Docs: Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode):
  `--json`, `turn.completed.usage`, `--output-last-message`, stdin 실행.
- [OpenAI Docs: Rules](https://learn.chatgpt.com/docs/agent-configuration/rules):
  `prefix_rule`, 복합 shell 처리, `codex execpolicy check`.
