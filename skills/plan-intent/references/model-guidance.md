# 설계 원칙과 공식 모델 가이드

스킬의 설계나 Astra 지침과의 대응을 검토할 때 읽는다. 개인 대화 기록을 전제하지 않는 공개 참고 문서다.

## 설계 원칙

원래 의도, 결정한 동작, 구현 방법을 구분한다. 정상·실패·허용하지 않는 결과를 구체적으로 설명해 이해 차이를 확인한다. 사용자의 이해, 선택, 실행 권한을 구분하되 불필요한 승인 단계를 만들지 않는다.

기획을 검토할 때는 다른 구현자가 새로운 중요한 선택 없이 작업과 검증을 설명할 수 있는지 살핀다. 구현 결과에 맞춰 원래 의도나 완료 기준을 소급 수정하지 않는다. 이 원칙들은 스킬의 설계 판단이며 특정 모델의 기능 보장을 뜻하지 않는다.

[Capture as intent.md](https://academy.claude.com/courses/ai-native-sdlc-playbook/capture-intent)는 요청자의 표현으로 문제·원하는 결과·대상·제약·열린 질문을 기록하고 오해를 수정하는 접근을 설명한다. 이 스킬은 그 의도 기록 방식을 참고하며, 기업용 승인 체계나 여러 산출물 파일을 필수 조건으로 요구하지 않는다.

## OpenAI GPT-6 Astra 가이드와의 대응

공식 문서 확인일: 2026-09-08. [latest-model 가이드](https://developers.openai.com/api/docs/guides/latest-model)의 확인 시점 제목은 “Using GPT-6 Astra”, 모델 표기는 `gpt-6-astra`였다.

| 공식 문서의 항목 | 스킬 적용 |
|---|---|
| [Initiative and follow-through](https://developers.openai.com/api/docs/guides/latest-model#initiative-and-follow-through) | 기존 합의 안에서 끝까지 진행하고 결과를 바꾸는 불확실성만 질문한다. 확인 전에 검토할 초안을 준비한다. |
| [Instruction following](https://developers.openai.com/api/docs/guides/latest-model#instruction-following) | 사용자 지시가 스킬의 일반 지침보다 우선한다. 스킬 때문에 중단하면 정확한 문구와 이유를 설명한다. |
| [Personality and writing style](https://developers.openai.com/api/docs/guides/latest-model#personality-and-writing-style) | 핵심부터 간결한 문단으로 설명하고 비교·순서에 필요한 구조만 사용한다. |
| [Subagent delegation](https://developers.openai.com/api/docs/guides/latest-model#subagent-delegation) | 독립 작업을 병렬로 맡기는 것이 시간·품질을 개선할 때 위임한다. |
| [Testing and verification](https://developers.openai.com/api/docs/guides/latest-model#testing-and-verification) | 작업에 맞는 검토를 수행하고 새 근거 없이 반복하지 않는다. |
| [Introduction](https://developers.openai.com/api/docs/guides/latest-model#introduction) | 중간 수정과 부가 질문을 반영하면서 전체 목표를 유지한다. |

공식 지침을 기획 대화에 맞게 적용한 것이며, 공식 문서가 특정 질문 양식이나 스킬 이름을 권장한다는 뜻은 아니다. Markdown 전용 구성과 기본 한국어 문체는 이 스킬의 설계 선택이다. 스킬 파일은 실행 모델이나 API 설정을 변경하지 않으며, Astra에서의 행동을 코드로 강제하지 않는다.

## 변경 시 확인할 행동

모호한 개인 프로젝트, 실패·취소 동작, 충분한 기존 계획, 답변의 이해 차이가 있는 가상 사례에 적용해 본다. 원래 의도 보존, 임의 선택 여부, 불필요한 재질문, 관찰 가능한 검증, 원문과 제안의 구분을 살핀다. 문서 형식 통과를 좋은 기획이나 장기적인 재작업 감소의 증명으로 취급하지 않는다.
