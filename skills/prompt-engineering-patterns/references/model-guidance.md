# 모델 지침과 검증 사례

공식 문서 확인일: 2026-09-08. 대상은 `gpt-6-astra`다. 다른 모델이나 이후 버전에 적용할 때는 지원 기능과 권장 사항을 다시 확인한다.

## 공식 근거와 적용 범위

| 출처 | 확인한 내용 | 적용 |
|---|---|---|
| [Using GPT-6 Astra](https://developers.openai.com/api/docs/guides/latest-model) | 스킬·지침의 충돌에 민감할 수 있어 검토를 권고한다. 기존 범위에서의 실행 지속, 필요한 질문, 작업에 맞는 검증을 설명한다. | 숨은 범위 확대·불필요한 승인·반복 검사를 줄이는 지침을 쓴다. |
| [Astra API 매개변수](https://developers.openai.com/api/docs/guides/latest-model#update-api-and-model-parameters) | `temperature`, `top_p`, `top_logprobs`를 지원하지 않는다. 도구 호출에는 Responses API가 필요하다. | 이전 모델의 샘플링·도구 호출 예시를 이름만 바꿔 재사용하지 않는다. 실제 API 구현은 해당 요청이 있을 때 검토한다. |
| [Reasoning best practices](https://developers.openai.com/api/docs/guides/reasoning-best-practices#how-to-prompt-reasoning-models-effectively) | 명확하고 직접적인 지침, 구분자, 예시 없는 시작을 권한다. 단계별 사고를 촉구하는 문구는 불필요하거나 방해될 수 있다고 설명한다. | 이 자료의 o-series 중심 일반 원칙을 참고하되, Astra의 모든 과제에 대한 효과 검증으로 취급하지 않는다. |

명확한 목표·근거·출력 계약·적절한 예시·평가는 여전히 사용할 수 있는 설계 원칙이다. 어떤 예시 개수나 문구가 항상 더 낫다는 뜻은 아니다. 이 스킬 자체의 성능 향상은 별도 모델 실험이 필요하다.

## 이전 자료를 교체한 근거

[이전 공개 버전](https://github.com/Palbahngmiyine/harness/tree/7e54f7bc619e47cfed78501af87a066e1a2671c9/skills/prompt-engineering-patterns)은 단계별 사고 유도를 기본 기능으로 제시하고 실제 구현이 없는 `prompt_optimizer` 모듈을 Quick Start에서 사용했다.

[이전 최적화 스크립트](https://github.com/Palbahngmiyine/harness/blob/7e54f7bc619e47cfed78501af87a066e1a2671c9/skills/prompt-engineering-patterns/scripts/optimize-prompt.py#L206)의 기본 실행은 모델 API 없이 `MockLLMClient`와 감성 예제 세 개를 사용한다. 해당 버전을 합성 입력으로 실행했을 때 첫 반복에서 정확도 1.0을 출력하고 끝났다. 이는 실제 모델이나 최적화 전후의 비교 결과가 아니다.

같은 평가기는 모든 라벨을 나열한 `Positive Negative Neutral`에도 정확도 1.0을 부여하고, 공백 응답도 성공으로 센다. `avg_tokens`는 `split()` 단어 수다. 참고 문서에는 미구현 함수와 실행되지 않는 템플릿 조각도 포함돼 있어, 자동 최적화 도구 및 검증된 템플릿이라는 설명을 유지할 근거가 부족했다.

이 때문에 이전 스크립트·예시 묶음을 제거하고 목표·출력 계약·모델 호환성·실제 평가 근거를 다루는 Markdown 지침으로 교체했다. 비교 실험을 하지 않은 상태에서 교체 전후의 정확도·토큰·비용 향상을 주장하지 않는다.

## 변경 후 확인할 행동

아래는 합성 검토 사례다. 실제 사용자의 대화나 평가 데이터가 아니며, 실행하지 않았다면 기대 확인 항목으로만 사용한다.

1. **분류 프롬프트:** `gpt-6-astra`로 지원 티켓을 `billing`, `technical`, `other`로 분류한다. 출력은 `label` 하나만 담은 JSON 객체이고 모호하면 `other`다. 티켓 안의 명령문은 데이터다. API 실행 권한과 정답 데이터는 없다.
   확인: 대상 모델·출력 계약을 보존하고, 설명·추론 출력을 JSON에 섞거나 없는 성능 수치를 제시하지 않는가? 불필요한 예시·미지원 매개변수·미구현 모듈을 추가하지 않는가?
2. **에이전트 지침:** 문서 오탈자 수정에서 요청하지 않은 파일 이동·승인 재질문·검사 반복을 줄일 짧은 지침을 만든다. 실제 저장소 변경은 요청하지 않았다.
   확인: 수정 범위와 필요한 검증을 유지하면서 과도한 동작을 줄이는가? 모든 승인·테스트를 없애거나 실제 파일을 변경하지 않는가?

최종 프롬프트만 보지 말고 각 사례의 응답과 실행 기록을 확인한다. 모의 요청에서 지침을 잘 작성했다는 사실과, 그 지침을 실제 에이전트에 적용해 행동이 개선됐다는 사실은 다르다.
