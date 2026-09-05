# 실행 사용량과 비용 비교

Hwahap은 `.hwahap/usage.json`에 사용량 관측값과 관측 시점을 저장한다. `hwahap_step`,
`hwahap_ship`, 검토 보고서 갱신 및 `usage sync`가 저장하며 `hwahap_status`와 `usage show`는 읽기 전용이다.
run을 archive하면 사용량과 기준값도 함께 보존한다. `.hwahap`은 Git에 추가하지 않는다.

## 로컬 Codex 사용량 연결

사용할 v3 바이너리의 launcher에 아래 인자를 전달한다. 먼저 Hwahap run을 시작하고 해당 실행에
참여하는 부모·자식의 정확한 로컬 Codex session JSONL 경로를 연결한다. 전역 설정 변경은 없다.

```sh
skills/hwahap/bin/hwahap usage attach /absolute/repository /absolute/rollout-session.jsonl
skills/hwahap/bin/hwahap usage sync /absolute/repository
skills/hwahap/bin/hwahap usage show /absolute/repository
```

기본 attach는 **현재 누적값을 기준값으로 저장하고 이후 증가분만** 집계한다. 동일 attach를 다시
실행해도 기준값이 움직이지 않는다. 재사용한 부모·자식의 이전 run 사용량을 포함하지 않기 위해서다.
처음부터 해당 run만 수행한 새 자식의 전체 사용량은 attach 끝에 `--from-start`를 붙여 연결할 수 있다.
이 옵션은 기존 세션의 과거 작업·상속된 사용량도 포함할 수 있으므로 새 세션에만 사용한다.
호스트가 정확한 경로를 알 수 없으면 해당 사용량은 미계측으로 남긴다. 임의 숫자를 만들지 않는다.

수집기는 `session_meta`, `turn_context`, `event_msg/token_count`의 숫자만 추출한다. 원본 대화,
추론 본문, 도구 출력은 `.hwahap`에 복사하지 않는다. 현재 로그 형식은 로컬 파일 관찰에 기반한
호환 어댑터이며 공식적으로 고정된 API라고 주장하지 않는다. 같은 세션은 한 번만 집계하고,
중복 누적 이벤트·부분 기록은 이중 합산하지 않는다. 파일 교체·누적값 감소·누락·64 MiB 초과는
`unavailable_sessions`에 표시한다. 해당 세션을 0비용으로 해석하지 않는다.

`observed_session_usage`는 연결된 세션의 부모 전달·계획·실패·재사용 작업을 포함하는 관측값이다.
`total`/`by_requested_model`은 별도로 native completion이 보고한 dispatch 사용량이다.
두 집계는 **겹치므로 더하지 않는다**. 캐시 입력은 전체 입력의 부분이며 reasoning 출력도 이미
전체 출력에 포함된다. 미연결 세션, attach 이전 작업, 아직 기록되지 않은 이벤트는 빠져 있다.
모델별 값은 로그에 기록된 모델 문맥 기준이며 서비스의 실제 모델 적용이나 청구 증명은 아니다.

## 선택적 비용 추정

사용 계정의 단가를 확인한 뒤 `.hwahap/pricing.json`을 둔다. 예를 들어 아래는 2026-09-06에
확인한 [Codex Standard credit 표](https://learn.chatgpt.com/docs/pricing)의 텍스트 단가다.
Fast mode, 계약별 단가, 도구 요금, 긴 문맥 등의 추가 요금은 자동 적용하지 않는다.

```json
{
  "currency": "credits",
  "source": "https://learn.chatgpt.com/docs/pricing",
  "effective_date": "2026-09-06",
  "assumptions": "Standard text rates only; excludes speed, contract and other surcharges",
  "per_million": {
    "gpt-6-astra": {"input": 250, "cached_input": 25, "output": 1250},
    "gpt-5.6-terra": {"input": 50, "cached_input": 5, "output": 300},
    "gpt-5.6-luna": {"input": 5, "cached_input": 0.5, "output": 30}
  }
}
```

단위는 백만 토큰당 가격이다. cache write가 관측되면 해당 모델의 `cache_write_input` 단가도
필요하다. 알려지지 않은 모델·write 단가는 `unpriced_models`에 남긴다. 금액은
`cost_estimate.priced_subtotal`이며 **실제 전체 청구금액이 아니다**. 단가표가 없거나 잘못돼도
토큰 관측값은 유지한다. 원래 단가 출처·유효일·가정을 보고서에 함께 남긴다.

## 모델 배치 비교

기본 PLAN은 Luna 첫 구현, Astra 검토·재작업이다. 중간 난도 구현에 Terra를 평가하려면
새 부모 pool에서 `.hwahap/config.toml`에 아래처럼 세 profile을 명시한다. 기존 pool의 모델은
바꾸지 않는다. direct BUILD는 기존 계약대로 부모 Astra와 별도 Astra 검토자 둘을 사용한다.

```toml
[profiles.economy]
model = "gpt-5.6-terra"
effort = "medium"
[profiles.critic]
model = "gpt-6-astra"
effort = "high"
[profiles.deep]
model = "gpt-6-astra"
effort = "high"
```

동일한 요청·base commit·acceptance·테스트로 Luna와 Terra 실행을 비교한다. `evaluation`의
run 상태·통과 unit 수·수정 시도·요청 profile, `latency`, 계측 범위와 토큰·추정 비용을 함께 본다.
실패·중단된 실행 비용도 포함한 성공 작업당 비용을 비교하고, 검증 기준을 낮춰 절감을 만들지 않는다.
대표 과제와 회귀 반례로 품질 기준을 먼저 고정한다. 측정 없이 모델 이름만으로 최적 배치를 단정하지 않는다.

PR 공격·방어의 초기 brief에는 전체 diff 대신 정확한 base/head와 변경 경로 목록을 담는다.
두 검토자는 그 revision의 실제 diff와 필요한 주변 소스를 직접 읽어 근거를 작성한다.
경로 목록은 검토 증거가 아니며, 큰 diff의 앞부분을 잘라 전달해 검토했다고 간주하지 않는다.

공식 모델 설명은 [Astra](https://developers.openai.com/api/docs/models/gpt-6-astra),
[Terra](https://developers.openai.com/api/docs/models/gpt-5.6-terra),
[Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna)를 따른다.
[App Server](https://learn.chatgpt.com/docs/app-server)는 `thread/tokenUsage/updated`를 제공한다.
호스트가 직접 이 이벤트를 받을 수 있으면 실제 counters를 전달할 수 있지만, 현재 MCP 도구가
그 이벤트를 자동 구독한다고 가정하지 않는다. 수집·비교 방향은
[Uber의 측정·문맥 비용·작업별 평가](https://www.uber.com/us/en/blog/efficient-software-factory/)를 참고했다.
