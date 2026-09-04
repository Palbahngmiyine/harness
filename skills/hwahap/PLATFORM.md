# 검증된 플랫폼 사실

Hwahap v3의 구조는 아래 사실 위에 서 있다. 전부 2026-09-04에 실제 실행으로 확인했고, 기억이나 문서
요약이 아니라 소스 위치와 관측 결과를 근거로 적었다. 어댑터나 SDK를 올릴 때는 이 파일을 다시 검증하고
날짜와 버전을 갱신한다.

| 대상 | 버전 | 확인 방법 |
|---|---|---|
| rustc / cargo | 1.98.1 (CI와 동일) | `rustc --version` |
| `agent-client-protocol` | 2.0.0 | crates.io, vendored source |
| `agent-client-protocol-schema` | 1.5.0 | 위 크레이트의 의존성 |
| `rmcp` | 3.2.0 (features `server`, `transport-io`, `macros`) | crates.io, vendored source |
| `@agentclientprotocol/codex-acp` | 1.7.0 | `codex-acp --version` |
| `codex` CLI | 0.152.1 | `codex --help` |
| 협상된 MCP protocol version | `2025-11-25` | initialize 응답 실측 |
| 협상된 ACP protocol version | v1 (stable) | initialize 응답 실측 |

## 1. ACP: model과 effort는 프로토콜 필드가 아니다

ACP v1 스키마에는 `session/set_model`도, `ModelId`도, 어떤 응답에도 `models` 필드도 없다. 두
크레이트 전체를 grep한 결과가 0건이다. model과 reasoning effort는 **session config option**이고,
어댑터가 무엇을 제공하는지에 전적으로 달려 있다.

`codex-acp` 1.7.0의 `session/new`가 돌려주는 config option은 정확히 5개다.

```
mode               (category: mode)               select, 기본 "agent"
collaboration_mode (category: Other("collaboration_mode")) select
model              (category: model)              select, 값은 effort 접미사 없는 base id
reasoning_effort   (category: thought_level)      select
fast-mode          (category: model_config)       client capability에 따라 boolean 또는 select
```

`model` 값에는 `gpt-5.6-luna`, `gpt-5.6-terra`, `gpt-5.6-sol`이 모두 있고 `reasoning_effort` 값에는
`low, medium, high, xhigh, max` (+ 일부 모델의 `ultra`)가 있다. 즉 세 profile 모두 적용 가능하다.

### 1.1 순서가 중요하다 — 실측으로 확인된 함정

`reasoning_effort`의 값 목록은 **선택된 모델에 따라 달라진다.** `gpt-5.6-sol`에서는 6개
(`low..ultra`)지만, `set_config_option`으로 `gpt-5.4-mini`로 바꾸면 4개(`low..xhigh`)로 줄어든다.

따라서 `session/new` 응답 한 장으로 model과 effort를 함께 검증하는 순서는 **틀렸다.** 기본 모델
기준으로 존재하는 effort를 통과시킨 뒤 어댑터가 거부하게 된다. `acp.rs`는 이렇게 한다.

```
session/new
  → model 옵션이 원하는 값을 제공하는지 확인
  → set_config_option(model)          ← 응답이 갱신된 전체 옵션 집합을 echo 한다
  → 그 응답에서 effort 옵션을 다시 확인   ← 여기서 처음 effort를 검증한다
  → set_config_option(reasoning_effort)
  → echo된 currentValue로 적용 결과 확인
  → 여기까지 통과해야 session/prompt
```

하나라도 어긋나면 `blocked: unsupported_profile`이다. `high`로 내려가지 않는다.

### 1.2 오류 모양

- 잘못된 config 값과 잘못된 config id 모두 `-32602 "Invalid params"`, `data` 없음.
- (스키마 밖) `session/set_model`의 알 수 없는 모델은 `-32603`에 `data.details` 포함.

Hwahap은 스펙에 있는 `set_config_option` 경로만 쓴다. `session/set_model`은 한 번에 둘 다 설정할 수
있지만 `{}`만 돌려주므로 적용 결과를 읽어 확인할 수 없다. 확인할 수 없는 경로는 fail-closed 정책과
맞지 않는다.

### 1.3 그 밖에 확인한 것

- 전송은 NDJSON이다. LSP `Content-Length` 프레이밍이 아니다. 번들에 있는 `Content-Length` 코드는
  어댑터가 내부적으로 쓰는 Codex app-server용이다.
- `session/new` 직후 요청하지 않은 `session/update`(`available_commands_update`) 알림이 비동기로
  도착한다. 클라이언트는 이를 견뎌야 한다.
- 어댑터가 `session/new`에 스키마 밖 `models` 객체를 함께 돌려주지만, `NewSessionResponse`에는 그
  필드가 없고 catch-all도 없어 serde가 조용히 버린다. 모델 목록은 `configOptions`로만 도달 가능하다.
- `AcpAgent`는 자식을 자기 프로세스 그룹(`process_group(0)`)에서 띄우고 drop 시 그룹 전체를 SIGKILL
  한다. `npx` 래퍼를 거쳐도 고아 프로세스가 남지 않는 근거다.
- ClientCapabilities를 기본값(fs·terminal 전부 false)으로 광고하면 SDK가 `fs/*`와 `terminal/*`을
  method-not-found로 알아서 거절한다. Hwahap이 핸들러를 쓰지 않는 이유다.
- `session/close`는 `AgentCapabilities.session_capabilities.close`로 게이트된다.
- `Responder::respond`는 `#[must_use] Result`이고, 그것이 request 핸들러의 반환값이다.

## 2. rmcp: 세 가지 함정

1. **`#[tool_router]`가 만드는 생성자는 기본이 private다.** `vis = "pub"`을 주지 않으면 통합
   테스트에서 `Hwahap::tool_router()`를 부를 수 없어 "tool 3개" 게이트가 닿지 않는다.
2. **stdio 서버는 그냥 두면 종료되지 않는다.** `tokio::io::stdin()`이 blocking pool 스레드를 EOF
   전까지 `read`에 붙잡아 두고, 런타임 drop이 그 pool을 기다린다. cancel 후 `waiting()`이 정상
   반환해도 프로세스가 살아 있다. `main`은 `std::process::exit(0)`으로 끝낸다. 실측: 수정 전 SIGINT
   후 10초가 지나도 생존, 수정 후 0.00초에 exit 0.
3. **`#[tool_handler]`에 `name`을 주지 않으면 서버가 자신을 `rmcp` 3.2.0이라고 소개한다.**
   `env!` 매크로가 rmcp 크레이트 안에서 전개되기 때문이다. `mcp.rs`는 `get_info`를 직접 쓴다.

그리고 **rmcp는 tool 호출을 동시에 디스패치하며 직렬화하지 않는다.** 관측된 와이어 트레이스에서 id 4의
응답이 id 3보다 먼저 나갔다. one-active-run 불변식은 프레임워크가 지켜주지 않으므로 `mcp.rs`가
`step`과 `ship`에 뮤텍스를 건다. `status`는 원자적으로 교체되는 파일만 읽으므로 걸지 않는다.

`Parameters<T>`와 `JsonObject`는 둘 다 `context.arguments.take()`를 호출해서 함께 쓰면 나중에
실행되는 쪽이 빈 객체를 받는다. 컴파일도 되고 200도 나오는 조용한 오작동이라, Hwahap은
`Parameters<T>`만 쓴다.

## 3. Codex 플러그인 규약

`~/.codex/skills/.system/plugin-creator/`가 이 머신의 규범 문서이고 `scripts/validate_plugin.py`가
사실상의 스키마다. 확인한 것:

- 매니페스트는 `.codex-plugin/plugin.json`이어야 한다. `.codex-plugin`은 파일이 아니라 **디렉터리**다.
- 최상위 키 허용 목록은 정확히 13개다. `hooks`는 참조 문서에 나오지만 validator가 거부한다.
- 필수: `name`, 엄격한 semver `version`, `description`, `author.name`, 그리고 `interface`의
  `displayName`·`shortDescription`·`longDescription`·`developerName`·`category`·`capabilities`·
  `defaultPrompt`.
- 스킬은 `<plugin>/skills/<skill-name>/SKILL.md`에 있어야 한다. 프론트매터는 `name`과 `description`
  둘 다 필수이고, Codex와 Claude Code 양쪽에서 안전한 교집합도 그 둘뿐이다.
- `.mcp.json`은 `{"mcpServers": {...}}` 하나만 최상위에 허용한다. Codex 형식은 `env_vars`(이름
  **배열**)와 `cwd`를 쓴다. Claude Code 형식의 `env`(객체)와 다르다.
- 설치 시 플러그인 디렉터리가 `$CODEX_HOME/plugins/cache/<marketplace>/<plugin>/<version>/`으로
  **그대로 복사**된다. 따라서 실행 파일은 플러그인 디렉터리 안에 있어야 하고, OpenAI 자체 플러그인도
  같은 이유로 `bin/`에 sh 런처를 둔다.

### 3.1 스킬 경로는 협상 불가능하다

플러그인 스킬을 `<plugin>/skills/<name>/` 밖에 둘 방법은 없다.

- `validate_skill_manifests`는 `skills_root = plugin_root / "skills"`를 **하드코딩**하고 그 바로
  아래 디렉터리만 순회한다 (`scripts/validate_plugin.py:424-431`).
- `plugin.json`의 `skills` 필드로 우회할 수 없다. `"skills": "./SKILL.md"`로 설치를 시도하면
  ``plugin.json field `skills` must resolve to `skills` ``로 거부된다 (실측). 이 필드는 경로를
  바꾸는 것이 아니라 기본 위치를 재확인하는 용도다.
- 이 머신에 있는 실제 플러그인의 스킬 **617개 중 플러그인 루트에 `SKILL.md`를 둔 것은 0개**다.
  (`find ~/.codex/.tmp/plugins/plugins ~/.codex/.tmp/bundled-marketplaces -maxdepth 2 -name SKILL.md`)
- `skills` 필드를 아예 빼고 루트에 `SKILL.md`를 둔 플러그인은 validator를 통과하고
  `codex plugin add`도 성공하며 파일도 캐시로 복사된다. 그러나 설치기는 디렉터리를 통째로 복사할
  뿐이므로, 이것은 **발견된다는 증거가 아니다.** 위 세 가지 근거를 볼 때 그런 스킬은 설치는 되지만
  발견되지 않을 가능성이 높다 — 겉보기에는 멀쩡한 가장 나쁜 실패다.

**결론**: hwahap은 Codex 플러그인으로 배포하지 않는다. 플러그인으로 만들려면
`skills/hwahap/skills/hwahap/SKILL.md`가 되어야 하는데, 이는 이 저장소가 나머지 7개 스킬에 쓰는
`skills/<name>/SKILL.md` 규약과 어긋나고 루트 README의 `cp -r skills/*` 설치를 깨뜨린다. 대신
스킬은 평범한 스킬 디렉터리로, MCP 서버는 `codex mcp add`로 등록한다. 후자는 실측으로 확인된
경로다(§3.2).

### 3.2 `codex mcp add`가 쓰는 TOML

격리된 `CODEX_HOME`에 대해 `codex mcp add hwahap --env FOO=bar -- /path/to/hwahap serve --flag`를
실행하면 `config.toml`에 다음이 기록된다.

```toml
[mcp_servers.hwahap]
command = "/path/to/hwahap"
args = ["serve", "--flag"]

[mcp_servers.hwahap.env]
FOO = "bar"
```

사용자의 실제 `~/.codex/config.toml`도 같은 모양이며, 선택적으로 `cwd`, `enabled`,
`startup_timeout_sec`을 받는다.

## 4. 알려진 제약: Windows

Hwahap은 frozen plan의 test 명령을 `sh -c`로 실행한다. 사람이 쓰는 그대로의 명령(파이프, 플래그)을
받기 위해서이지만, 그 대가로 **POSIX shell이 필요하다.** 통합 테스트 하네스도 같은 이유로 POSIX
`sh`를 쓰고, 따라서 `runtime/tests/cycle.rs`는 `#![cfg(unix)]`다.

Windows에서 단위 테스트는 전부 돌지만 사이클은 검증되지 않았고, Git Bash가 PATH에 없으면 unit test
실행 자체가 실패한다. 이것은 테스트만의 문제가 아니라 제품의 제약이다. Windows를 지원하려면
`sh -c`를 플랫폼별 shell 선택으로 바꾸고 하네스를 다시 써야 한다.

## 5. 아직 검증하지 않은 것

정직하게 남겨 둔다. 아래는 설계가 의존하지만 실측하지 못했다.

- ChatGPT Desktop이 `codex mcp add`가 쓴 `config.toml`을 CLI와 같게 읽는지. CLI 0.152.1만 확인했다.
- Codex 샌드박스(`workspace-write`) 아래에서 MCP 서버가 `codex-acp` 같은 장수명 자식 프로세스를
  띄울 수 있는지. **v3의 핵심 가정이며 미검증이다.**
- 플러그인 루트에 놓인 `SKILL.md`가 정말로 발견되지 않는지. §3.1의 세 근거가 그렇게 가리키지만,
  발견 여부를 직접 관측할 방법을 찾지 못했다. hwahap이 플러그인 배포를 쓰지 않으므로 결론에는
  영향이 없다.
- `session/prompt` 중 어댑터가 `fs/*`, `terminal/*`, `session/request_permission`을 실제로 호출하는
  경로. 프롬프트를 보내는 프로브는 quota 때문에 최소한으로만 돌렸다.
- `session/cancel` → `StopReason::Cancelled` 왕복.
- `max`/`ultra` effort를 실제로 설정했을 때의 동작과 과금. 목록에 존재한다는 것만 확인했다.
- 어댑터의 프로세스 그룹 kill이 실제로 고아를 남기지 않는지의 행동 검증(소스만 읽었다).
