# 출처와 설계 범위

다음 공식 자료의 본문을 확인했다. 아래의 일기 운영 방식은 교육용 질문법을 이 요청에 응용한 설계이며, 효과가 검증된 치료 프로그램이나 성격 평가 도구라는 뜻이 아니다.

| 출처 | 본문에서 확인한 내용 | 스킬에 적용한 방식 |
|---|---|---|
| [OpenAI — Build skills](https://learn.chatgpt.com/docs/build-skills) | `SKILL.md`에 `name`과 `description`이 필요하며 scripts, references, UI 설정은 선택 사항이다. 전체 본문과 참고 자료를 필요한 때 읽는다. | `.md` 파일만 사용하고 질문 예시와 설계 출처를 필요할 때 읽는다. |
| [University of Connecticut CETL — Socratic Questions](https://cetl.uconn.edu/resources/teaching-your-course/leading-effective-discussions/socratic-questions/) | 답에 이어 질문하고 주기적으로 요약하며, 가정·증거·다른 관점·결과·질문 자체를 탐색한다. | 답에 따른 후속 질문, 대안 해석, 선택의 이익과 비용을 검토한다. |
| [University of Michigan — Summary Notes](https://public.websites.umich.edu/~scps/html/03chap/html/summary.htm) | 결론·근거·가정을 구분하며, 결론을 기각할 증거와 빠진 정보를 묻는다. | 관찰과 해석을 구분하고 반대 사례·누락된 상황을 확인한다. |

## 질문 선택과 개인화의 범위

질문 예시는 여러 상황에서 선택해 사용할 수 있는 대화 지침이다. 실행 시 사용자가 제공하거나 접근 가능한 기록에서 구체적인 장면을 확인하고, 그날의 답변에 맞는 질문을 고른다. 개인 대화 원문·식별자·프로필은 배포 파일에 포함하지 않는다.

질문 축은 `근거의 충분성`, `준비와 직접 실행`, `공동 결과와 독립 이해`, `목표의 초점`, `가역적 선택의 위임`이다. 특정 사용자의 성향이나 단점을 나타내는 분류가 아니며, 맞지 않는 질문은 생략한다. AI의 오류나 도구 실패가 반복의 원인일 수도 있다. 에이전트 밖의 생활은 코딩 에이전트의 대화 기록만으로 알 수 없다.

한 번에 한 질문, 약 10분의 기본 깊이, 두 생활 영역, 작은 선택 하나, 다음 일기의 후속 확인은 이 스킬의 운영 제안이다. 위 문서가 이 조합의 효과를 직접 입증하지 않는다. 일기 문답은 별도 자동 수집·복습 체계 없이 사용할 수 있다.

## 대화 기록 조회의 근거

[오늘의 대화 기록 찾기](record-lookup.md)는 macOS 환경에서 Claude Code와 Codex CLI가 남긴 로컬 파일을 직접 읽어 정리한 것이며, 확인한 버전 계열은 그 문서의 머리말에 적는다. 두 도구의 공식 문서가 보장하는 안정된 API가 아니라 관찰한 저장 형식이므로 파일명 접미사·테이블·필드는 업데이트로 바뀔 수 있다. 조회 예시는 읽기 전용 참고이며 이 저장소의 문서 전용 방침 안에서 스크립트를 대신하지 않는다.

공식 문서가 설명하는 저장 루트와 직접 관찰한 내부 형식을 구분한다. [OpenAI — Config and state locations](https://developers.openai.com/codex/config-advanced/#config-and-state-locations)는 `CODEX_HOME`과 기본 `~/.codex`를, [Claude Code — Find or create your settings files](https://code.claude.com/docs/en/settings#find-or-create-your-settings-files)는 `CLAUDE_CONFIG_DIR`로 설정·세션 기록 등의 위치를 옮길 수 있음을 설명한다. SQLite 테이블·JSONL 필드·각 전용 조회 도구의 출처 범위는 실행 환경에서 별도로 확인한다.

장기 goal의 당일 진행은 진행 중인 로컬 작업에서 전용 조회의 최근 턴 본문이 비어 있어도 원본에 당일 진행·완료 이벤트가 남은 사례를 읽어 보완했다. 개별 이벤트 시각으로 이전 상태와 당일 변화를 구분하는 규칙이며, 특정 내부 필드가 모든 버전에서 같다고 보장하지 않는다. 실제 대화 제목·식별자·원문은 배포 자료에 포함하지 않는다.

## 역학 연습의 근거와 한계

아래 자료의 본문(학회 발표본·재게시본 포함)을 확인했다. 개인 저널링에 system dynamics를 적용한 통제 연구는 찾지 못했고, Sterman 1994 "Learning in and about complex systems"(System Dynamics Review 10)는 초록만 확인했다. [역학 연습 진행표](dynamics-practice.md)의 연습이 이해력을 높인다는 직접 증거는 없다.

설계 근거는 세 가지다. 첫째, 사람이 쌓임·지연·피드백을 오인할 수 있다는 연구(Booth Sweeney & Sterman 2000, Cronin 등 2009, Sterman 2001)가 "무엇이 쌓였나"를 묻는 이유다. 둘째, 직접 다뤄 보기와 결과 피드백을 살핀 실험(Moxnes & Saysel 2004)을 참고해 사용자 식별과 후속 관찰을 둔다. 셋째, 언어형 질문 연구(Fischer & Degen 2012)를 참고해 말로 설명하게 한다. 각 연구를 모든 설명·개인 일기·LLM 협업에 일반화하지 않는다. "도움이 된 느낌"과 예측 한 번의 적중은 측정된 학습 효과와 다르다(Green 등 2022).

LLM 작업의 이해를 맞추기 위한 `사용자 첫 설명 → 조건 변화 예측 → 코드·문서·실행 근거 대조 → 설명 수정`은 이 스킬의 설계다. 첫 답 전에 모범 답안을 주지 않는 것과 답 이후 근거에 맞게 교정하는 것을 구분한다. 소크라테스식 문답을 이유로 확인된 사실 오류를 그대로 두거나 질문만 반복하지 않는다. 이 흐름의 장기 효과는 실제 사용에서 별도로 확인해야 한다.

채택하지 않은 요소와 이유: AI가 그리는 인과 루프 다이어그램(Forrester, Richardson, Sterman 2002가 시뮬레이션 없는 루프 추론을 경고), 시스템 원형 이름(정의가 합의되지 않았고 이 스킬의 진단 금지와 충돌), 개입 지점 순위(Meadows 본인이 "Leverage points are not intuitive… we intuitively use them backward"라고 썼다, https://donellameadows.org/archives/leverage-points-places-to-intervene-in-a-system/ 웹 게시 글 확인), 수치 모델(10분 대화로 불가), 짧은 강의식 설명(Sterman 2010이 단기 노출의 비효과를 명시). 시뮬레이션은 능동 통제군 대비 유의한 효과를 보인 유일한 요소였지만 이 형식으로 제공할 수 없어 방향 예측과 다음 저녁 확인으로 대체했다. 이 대체가 같은 효과를 낸다는 증거는 없다.

| 출처 | 본문에서 확인한 내용 | 스킬에 적용한 방식 |
|---|---|---|
| [MIT OCW 15.871 Introduction to System Dynamics (Fall 2013)](https://ocw.mit.edu/courses/15-871-introduction-to-system-dynamics-fall-2013/pages/syllabus/) | 목표 "recognize and deal with situations where policy interventions are likely to be delayed, diluted, or defeated by unanticipated reactions and side effects"; 주제 stock/flow, feedback, causal loop diagrams; 후속 15.872는 시뮬레이션 중심 | 4단계 정책 저항의 질문 소재. 시뮬레이션은 제공하지 않는다. |
| [Sterman 2001, "System Dynamics Modeling: Tools for Learning in a Complex World", California Management Review](https://faculty.sites.iastate.edu/tesfatsi/archive/tesfatsi/SystemDynamics.JohnSterman2001.pdf) | 가장 어려운 요소 "feedback, time delays, stocks and flows (accumulations), and nonlinearity"(p.11); 피드백은 강화·균형 두 종류(p.17); "people commonly ignore time delays, even when the existence and contents of the delays are known"(p.13) | 진행표의 네 요소, 2·3단계 질문. |
| [Sterman 2002, "All models are wrong", System Dynamics Review](https://web.mit.edu/jsterman/www/All_Models_Are_Wrong_(SDR).pdf) | 개념 지도만으로 충분하다는 주장에 "They are mistaken. Simulation is essential"(p.524); 질문자에서 전문가·교사 역할로 옮기면 방어를 낳는다(p.522) | 초기 설명은 사용자에게 맡긴다. 방향 예측을 시뮬레이션과 동등한 검증으로 취급하지 않는다. |
| [Booth Sweeney & Sterman 2000, "Bathtub dynamics"](https://web.mit.edu/jsterman/www/Bathtub.pdf) | 경영대 학생도 스톡·플로우·지연 이해가 낮고 학력·연령과 무관; "there is little evidence, or even systematic research, to support educators' and consultants' faith in its efficacy"(p.1) | 1단계를 두는 이유(진단). 효과 주장 문구 금지. |
| [Cronin, Gonzalez & Sterman 2009, Organizational Behavior and Human Decision Processes](https://www.mit.edu/~jsterman/CroninGonzalezSterman061210.pdf) | 상관 휴리스틱 "output should 'look like' the input"(p.5); MIT Sloan 대학원생 173명 중 유입·유출 정답 95% 이상, 재고 최대 시점 정답 44%; 표시 형식·인센티브로 개선 실패 | 1단계 점검 질문. |
| [Sterman 2010, "Does formal system dynamics training improve people's understanding of accumulation?" (2009 학회 발표본)](https://proceedings.systemdynamics.org/2009/proceed/papers/P1113.pdf) | 반학기 11회 과정 후 오답률 46.1%→24.7%; 짧은 워크숍은 "unlikely to be effective"; 교실 밖 전이 미검증 | 매일 요소 하나씩 반복하는 진행표. 단기 노출로 효과를 주장하지 않는다. |
| [Moxnes & Saysel 2004](https://proceedings.systemdynamics.org/2004/SDS_2004/PAPERS/277MOXNE.pdf) | 유추를 설명으로 제공(T2)·규칙 제시(T3)는 효과 없음; 같은 유추 안에서 직접 조작(T1)·다회 결과 피드백(T4)은 효과 | 초기 답을 사용자가 직접 짚게 하고 예측을 후속 관찰과 비교하는 설계에 참고. |
| [Fischer & Degen 2012](https://proceedings.systemdynamics.org/2012/proceed/papers/P1434.pdf) | 언어형으로 물으면 정답률이 86%까지 상승 | 그래프·도표 없이 말로 묻고 답한다. |
| [Green, Molloy & Duggan 2022, Sustainability 14(1)](https://www.mdpi.com/2071-1050/14/1/394) | 능동 통제군 무작위 대조 실험(n=106): 시뮬레이션 d=0.6 유의, 시스템 사고 교육 d=0.4 비유의; 참가자 74.1%가 크게 도움됐다고 답했으나 점수 차이 비유의 | "도움이 된 느낌"을 효과 증거로 쓰지 않는다. 효과는 예측 확인과 사용자 판단으로만. |
| [Repenning & Sterman 2001, California Management Review](https://web.mit.edu/nelsonr/www/Repenning=Sterman_CMR_su01_.pdf) | 작업 압력이 늘면 개선 시간이 줄고 역량이 감퇴하는 순환(pp.70–71); 지연(p.72); worse-before-better(p.73); "the structure of the system inadvertently leads"(p.78); 개인 삶 확장 언급(p.75) | 구조 귀인(성격 대신 조건). 4단계 질문. 개인 적용의 1차 근거는 이 문단 하나이며 실증이 아니다. |
| [Forrester, D-4405-1 "System Dynamics, Systems Thinking, and Soft OR"](https://s3.amazonaws.com/static.clexchange.org/ftp/documents/roadmaps/RM7/D-4405-1.pdf) | "'Systems thinking' has no clear definition or usage"(p.10); 인과 루프 다이어그램은 "do not provide the discipline… imposed by level and rate diagrams"(p.11) | AI의 루프 그림 제시 제외. 순환 뒤의 스톡을 항상 묻는다. |
| [Richardson 1986, "Problems with causal-loop diagrams", D-3312-2](https://s3.amazonaws.com/static.clexchange.org/ftp/documents/roadmaps/RM4/D-3312-2.pdf) | "causal-loop diagrams obscure the stock and flow structure… Even experienced modelers are easily misled"; 비례 연결 가정은 대부분의 행동 추론을 틀리게 한다(p.167) | 즉석 루프 추론 대신 스톡 식별을 먼저 둔다. |
| [Senge 외, 추론의 사다리 (Fieldbook 재게시본)](https://cdn.edreports.org/legacy/files/Ladder-of-Inference-OCDE.pdf) | "What is the observable data behind that statement? … Can you run me through your reasoning?"; "The point of this method is not to nail Larry (or even to diagnose Larry)" | 불일치 확인 질문(“예측할 때 무엇을 가정했나요?”). 진단 금지. |

## 월요일 검증의 설계 범위

[지난 일기 조회와 월요일 검증](journal-review.md)의 호출일 요일 계산, 기준 월요일과 직전 월~일 범위, 같은 주의 미검증 시 한 번 보충하는 흐름, 완료 기록으로 중복을 막는 방식, 실행과 효과의 구분은 이 스킬의 운영 규칙이다. 특정 연구가 월요일이라는 요일이나 이 조합의 효과를 입증했다는 뜻이 아니다. 기록 부재를 행동 실패로 판정하지 않고, 사용자가 채택한 실천과 예측을 실제 후속 근거에 연결하는 데 목적이 있다. 스킬 호출 중의 조건부 동작이며 상주 수집기나 예약 자동화를 요구하지 않는다.

## 실제 사용에서 볼 것

사용자가 자기 말로 받아들인 해석이 있는지, 실천을 선택했는지, 다음 날 실행과 효과가 어땠는지, 문답이 부담스럽지 않았는지로 조정한다. 대화 횟수나 일기 분량 증가를 개선 증거로 삼지 않는다. 형식 검사와 모의 문답 검토만으로 장기간의 효과를 주장하지 않는다.
