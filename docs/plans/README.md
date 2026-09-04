# Plans

| Date | Plan | Status |
|---|---|---|
| 2026-09-04 | [Hwahap V3: 얇은 Skill과 단일 실행 루프](2026-09-04-hwahap-v3.md) | Proposed |
| 2026-09-04 | [Hwahap V3 모델·Reasoning Effort 정책](2026-09-04-hwahap-v3-effort-policy.md) | Normative for V3 |
| 2026-09-04 | [Hwahap V3 구현·검증 계획](2026-09-04-hwahap-v3-delivery.md) | Proposed |

Hwahap V3는 v2를 호환성 없이 전면 교체한다. 핵심 형태는 `thin Skill + local STDIO MCP + Rust binary + stable ACP v1`이다. 초기 구현은 한 repository당 active run 하나, run worktree 하나, adapter process 하나, active agent session 하나만 사용한다. SQLite, daemon, HTTP server, lifecycle hook, worker용 내부 MCP, parallel worker pool, v2 compatibility layer는 만들지 않는다.

모델 profile은 `Economy = GPT-5.6 Luna / medium`, `Critic = GPT-5.6 Terra / high`, `Deep = GPT-5.6 Sol / xhigh`로 고정한다. `max`/Ultra는 hidden agent fan-out과 사용량 변동 가능성 때문에 V3 초기 범위에서 제외한다.
