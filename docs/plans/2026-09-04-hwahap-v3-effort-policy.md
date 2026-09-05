# Hwahap V3 모델·Reasoning Effort 정책

- 상태: Hwahap V3 기획의 규범적 부속 문서
- 작성일: 2026-09-04
- 상위 기획: [Hwahap V3: 얇은 Skill과 단일 실행 루프](2026-09-04-hwahap-v3.md)
- 구현 계획: [Hwahap V3 구현·검증 계획](2026-09-04-hwahap-v3-delivery.md)

## 1. 결정

Hwahap V3는 모델 역할뿐 아니라 reasoning effort도 세 개의 고정 profile로 관리한다.

| Profile | 기본 모델 | Reasoning effort | ChatGPT 표현 | 담당 |
|---|---|---|---|---|
| Economy | `gpt-5.6-luna` | `medium` | Medium | fact 조사, cold consumer, routine implementation, tests, 첫 rework |
| Critic | `gpt-5.6-terra` | `high` | High | recommendation/plan 적대적 검토, unit review, 반복 실패 진단 |
| Deep | `gpt-5.6-sol` | `xhigh` | Extra High | alternatives와 recommendation, final plan synthesis, PlanConflict replan, final integrated review |

Hwahap이 사용하는 protocol/config 값은 `medium`, `high`, `xhigh`다. 이 문서에서 `Extra High`는 사용자에게 보이는 ChatGPT 명칭이고, `xhigh`는 Hwahap이 ACP/Codex session에 요청하는 값이다.

## 2. 공식 문서 근거

OpenAI의 GPT-5.6 ChatGPT 문서는 reasoning 수준을 다음과 같이 설명한다.

- Medium: 표준 reasoning
- High: 확장된 reasoning
- Extra High: GPT-5.6 Sol에서 제공되는 가장 높은 reasoning 수준

GPT-5.6 Luna, Terra, Sol의 공식 model 문서는 세 모델 모두 `none`, `low`, `medium`, `high`, `xhigh`, `max`를 지원하며 `medium`을 기본값으로 명시한다.

공식 자료:

- ChatGPT GPT-5.6 reasoning 수준: https://help.openai.com/en/articles/20001354-gpt-5-6
- GPT-5.6 Luna: https://developers.openai.com/api/docs/models/gpt-5.6-luna
- GPT-5.6 Terra: https://developers.openai.com/api/docs/models/gpt-5.6-terra
- GPT-5.6 Sol: https://developers.openai.com/api/docs/models/gpt-5.6-sol
- ChatGPT/Codex rate card: https://help.openai.com/en/articles/11481834-chatgpt-rate-card

## 3. Profile별 이유

### 3.1 Economy = Luna + `medium`

Economy는 단순 문자열 분류만 수행하는 profile이 아니다. Repository fact를 정확히 읽고, frozen contract에 맞춰 코드를 수정하고, acceptance에서 test를 작성해야 한다.

`low` 대신 `medium`을 고정하는 이유는 다음과 같다.

1. `medium`은 GPT-5.6 모델의 공식 기본 reasoning effort다.
2. 비용 절감은 이미 Luna model tier 선택으로 크게 확보된다.
3. Task별 `low`/`medium` 분기를 추가하면 단순화 원칙과 충돌하는 별도 effort router가 필요하다.
4. 잘못된 routine implementation으로 retry가 늘어나는 비용을 줄인다.

따라서 fact 조사, cold consumer, implementation, tests, 첫 rework는 모두 `medium`을 사용한다.

### 3.2 Critic = Terra + `high`

Critic은 생성자가 놓친 의미적 결함을 독립적으로 찾아야 한다. 단순 확인이 아니라 contract, failure mode, security, compatibility, test sufficiency를 공격적으로 검토한다.

ChatGPT 문서가 High를 확장된 reasoning으로 설명하므로 Terra Critic에는 `high`를 사용한다. `medium`은 routine verification과 구분되지 않고, `xhigh`는 Deep 역할과 경계를 흐린다.

### 3.3 Deep = Sol + `xhigh`

Deep은 다음과 같이 cross-cutting reasoning이 필요한 지점에만 사용한다.

- alternatives와 recommendation synthesis
- final plan synthesis
- PlanConflict impact analysis와 replan
- complete branch diff의 final integrated review

ChatGPT의 Extra High에 대응하는 Hwahap protocol 값으로 `xhigh`를 사용한다. Deep은 `xhigh`보다 낮은 effort로 자동 downgrade하지 않는다.

## 4. 사용하지 않는 effort

### `none`과 `low`

V3 기본 profile에는 사용하지 않는다. 이를 쓰려면 task classification과 fallback을 추가해야 하며, 현재 목표인 세 profile 고정 정책보다 복잡해진다. 실제 benchmark가 `medium` 대비 품질 저하 없이 유의미한 비용 절감을 증명하기 전에는 추가하지 않는다.

### `max`와 Ultra

V3 초기 범위에는 사용하지 않는다.

OpenAI의 ChatGPT/Codex rate card는 Ultra가 maximum reasoning을 사용하고, eligible user에서는 추가 Agent를 실행할 수 있다고 설명한다. 이는 Hwahap V3의 다음 불변식과 충돌할 수 있다.

- active ACP session 최대 1개
- hidden agent fan-out 없음
- 고정된 process budget
- 사용량과 evidence attribution의 예측 가능성

따라서 `max`, Ultra, Pro model은 Deep의 동의어가 아니다. Deep은 정확히 `gpt-5.6-sol` + `xhigh`다.

## 5. 설정 계약

설정은 model과 effort를 분리된 전역 표가 아니라 role profile 한 단위로 저장한다.

```toml
[profiles.economy]
model = "gpt-5.6-luna"
effort = "medium"

[profiles.critic]
model = "gpt-5.6-terra"
effort = "high"

[profiles.deep]
model = "gpt-5.6-sol"
effort = "xhigh"
```

이 구조는 model을 바꾸고 effort를 이전 모델 기준으로 남기는 configuration skew를 막는다.

## 6. Session 적용 규칙

각 ACP session은 시작 전에 profile을 완전하게 적용한다.

```text
role
  -> profile lookup
  -> advertised model 확인
  -> supported effort 확인
  -> model 설정
  -> reasoning effort 설정
  -> 적용 결과 확인
  -> prompt 시작
```

다음은 금지한다.

- 지원되지 않는 effort의 silent fallback
- `xhigh`를 `high`로 자동 downgrade
- `medium`을 `low`로 비용 최적화
- Parent session의 model/effort 상속
- Worker가 자기 model/effort를 변경
- retry 때 effort를 임의로 증가

요청한 model 또는 effort가 ACP session capability에 없으면 해당 run을 `blocked: unsupported_profile`로 종료한다. 사용자에게 실제 advertised models/efforts와 필요한 profile을 함께 보여준다.

## 7. Retry와 escalation

Retry는 effort escalation이 아니다.

```text
Economy/medium implementation
  -> deterministic verification
  -> Critic/high review
  -> Economy/medium rework once
  -> Critic/high diagnosis
  -> blocked 또는 plan conflict
```

Deep/xhigh는 routine implementation 실패를 해결하기 위해 자동 투입하지 않는다. Deep은 plan-level reasoning과 final integrated review에만 사용한다.

## 8. Evidence와 비용 귀속

모든 Agent receipt는 다음을 기록한다.

```json
{
  "profile": "economy",
  "model_requested": "gpt-5.6-luna",
  "model_applied": "gpt-5.6-luna",
  "effort_requested": "medium",
  "effort_applied": "medium",
  "role": "implementer",
  "unit": "U3"
}
```

`requested`와 `applied`가 다르면 prompt를 시작하지 않는다. Summary는 profile별 token usage를 분리한다.

OpenAI의 현재 model 문서 기준 API token 가격도 역할 선택의 방향과 일치한다. Luna는 cost-sensitive workload용이고, Terra는 intelligence/cost balance, Sol은 complex professional work용이다. 가격 자체는 변경될 수 있으므로 Hwahap gate에 hard-code하지 않고 보고서의 informational metadata로만 사용한다.

## 9. 구현·검증 기준

구현은 다음을 정적으로 검증한다.

- profile 수 = 3
- Economy effort = `medium`
- Critic effort = `high`
- Deep effort = `xhigh`
- default profile에 `none`, `low`, `max` 없음
- model과 effort를 role profile 밖에서 설정하는 production path 없음
- unsupported profile silent fallback 0
- receipt의 requested/applied model·effort 누락 0
- retry에 따른 effort mutation 0

Fake ACP test는 다음 case를 포함한다.

1. 세 profile 모두 정확히 적용됨
2. Economy model은 있지만 `medium`이 없으면 fail-closed
3. Critic에 `high`가 없으면 fail-closed
4. Deep에 `xhigh`가 없으면 fail-closed
5. Adapter가 다른 effort를 applied로 반환하면 prompt 전 중단
6. Retry가 원래 profile을 유지함
7. `max`가 advertised되어도 선택하지 않음

## 10. 기획 통합 규칙

이 문서는 상위 V3 문서의 “고정된 모델 역할”을 구체화한다. 구현 단계에서는 다음 mapping이 규범적이다.

```text
Economy = GPT-5.6 Luna / medium
Critic  = GPT-5.6 Terra / high
Deep    = GPT-5.6 Sol / xhigh
```

상위 문서나 PR 설명에서 모델만 표기하고 effort가 생략된 경우에도 이 mapping을 적용한다. 이 정책을 바꾸려면 단순 설정 수정이 아니라 benchmark evidence와 기획 문서 개정이 필요하다.
